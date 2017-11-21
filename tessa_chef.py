#!/usr/bin/env python

from collections import defaultdict
import json
import logging
import os
import re
import tempfile
import shutil
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
import jinja2
import requests

from le_utils.constants import content_kinds, file_formats, licenses
from ricecooker.chefs import SushiChef
from ricecooker.classes import nodes
from ricecooker.classes import files
from ricecooker.classes.files import HTMLZipFile
from ricecooker.classes.licenses import get_license
from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, TopicNode
from ricecooker.config import LOGGER
from ricecooker.exceptions import UnknownFileTypeError, raise_for_invalid_channel
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip







# Chef settings
################################################################################
DATA_DIR = 'chefdata'
TREES_DATA_DIR = os.path.join(DATA_DIR, 'trees')
CRAWLING_STAGE_OUTPUT_TPL = 'web_resource_tree_{}.json'
SCRAPING_STAGE_OUTPUT_TPL = 'ricecooker_json_tree_{}.json'
ZIP_FILES_TMP_DIR = os.path.join(DATA_DIR, 'zipfiles')


# TESSA settings
################################################################################
TESSA_HOME_URL = 'http://www.tessafrica.net/home'
TESSA_LANG_URL_MAP = {
    'en': 'http://www.open.edu/openlearncreate/course/view.php?id=2042',
    'fr': 'http://www.open.edu/openlearnworks/course/view.php?id=2046',
    'ar': 'http://www.open.edu/openlearnworks/course/view.php?id=2198',
    'sw': 'http://www.open.edu/openlearnworks/course/view.php?id=2199',
}

REJECT_TITLES = [
    # Overview pages that link to other modules --- TODO: scrape manually and process to remove link colors
    'Curriculum framework',
    'Résumé et récapitulatif des matériels TESSA',
    'طار المناهج',
    'Mfumo wa mtaala',
    # 'Download the complete Pan-Africa English library' # keeping bcs we can handle pdf
]

ADDITIONAL_RESOURCES_TITLES = [
    'Additional resources',
    'Autres ressources',
    'موارد المواد',
    'Nyenzo za zaidi',
    # 'Download the complete Pan-Africa English library' # keeping bcs we can handle pdf
]

TESSA_STRINGS = {
    'en': {
        'module': 'Module',
        'key resource': 'Key Resource',
    }
}
TESSA_LICENSE = get_license(licenses.CC_BY_NC_SA, copyright_holder='TESSA')


# Set up webcaches
################################################################################
sess = requests.Session()
cache = FileCache('.webcache')
basic_adapter = CacheControlAdapter(cache=cache)
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)
sess.mount('http://', basic_adapter)
sess.mount('https://', basic_adapter)
sess.mount('http://www.open.edu', forever_adapter)
sess.mount('https://www.open.edu', forever_adapter)



# LOGGING SETTINGS
################################################################################
logging.getLogger("cachecontrol.controller").setLevel(logging.WARNING)
logging.getLogger("requests.packages").setLevel(logging.WARNING)
logger = logging.getLogger('tessa')


# CRAWLING
################################################################################

# Looks at the top nav to get the current page subsection.
get_page_id = lambda p: get_text(p.find(id="page-navbar").find_all("span", itemprop='title')[-1])
get_text = lambda x: "" if x is None else x.get_text().replace('\r', '').replace('\n', ' ').strip()

# Used for modules that do not correspond to a single page ID.
get_key = lambda s: s.replace(" ", "_").replace("-","_").lower()

# Used for nodes that correspond to a single page (topics, sections).
url_to_id = lambda u: parse_qs(urlparse(u).query).get('id', '')



def get_modtype(activity):
    """
    Extract the type of activity --- link, resouce, label, subpage, etc.
    """
    classes = activity.get("class")
    for klass in classes:
        if klass.startswith('modtype_'):
            return klass.replace('modtype_', '')
    return None


def get_resource_info(item):
    """
    Process a list item in a top-level page or subpage and return info as dict.
    """
    link = item.find("a")
    if not link or not hasattr(link, "href"):
        raise ValueError('get_resource_info did not find link in item ' + str(item))

    source_id = url_to_id(link["href"])[0]
    title_span = item.find('span', class_="instancename")
    hidden_subspan = title_span.find("span", class_="accesshide")
    if hidden_subspan:
        hidden_subspan_text = get_text(hidden_subspan)
        hidden_subspan.extract()                 # remove resouce type indicaton
    else:
        hidden_subspan_text = None
    title = get_text(title_span)
    return {
        "url": link["href"],
        'source_id': source_id,
        "type": get_modtype(item),
        "title": title,
        'hidden_subspan_text': hidden_subspan_text,  # human-readbale equiv. of type
        'children': [],
    }


def extract_channel_description(first_label_activity):
    """
    Returns description text for a TESSA language page (All countries combined).
    This description lives in various forms in the first "label" activity in the list.
    Requires special language specifc hacks... and best effort to produce text.
    """
    description_pars = first_label_activity.find_all('p')
    pre_description = ' '.join([p.get_text().replace('\n',' ') for p in description_pars])
    description = pre_description.strip()
    return description


def extract_category_from_modtype_label(category):
    """
    Returns (action, title, description) for a TESSA top-level category.
    action is 'new' if this is really a new category
    action is 'append' if just decription to be appended to previous category
    """
    description_pars = category.find_all('p')

    # we'll now go on a journey looking for the title-containing HTML element
    title_el = None

    # A: see if there is a heading in a span
    #     title_span = category.find('span')
    #     if title_span:
    #         span_contents = title_span.get_text().replace('\n',' ').strip()
    #         print('span_contents', span_contents[0:20])

    if title_el is None:
        title_strongs = category.find_all('strong')
        for title_strong in title_strongs:
            title = title_strong.get_text().replace('\n',' ').strip()
            if len(title) > 0:
                title_el = title_strong
                # print('Strong title:', title)
                break

    if title_el is None:
        title_bs = category.find_all('b')
        for title_b in title_bs:
            title = title_b.get_text().replace('\n',' ').strip()
            if len(title) > 0:
                print('Bold title:', title)
                title_el = title_b
                break

    if title_el is None:
        title_h4 = category.find('h4')
        if title_h4:
            title = get_text(title_h4)
            if len(title) > 0:
                print('H4 title:', title)
                title_el = title_h4

    if title_el is None:
        pre_description = ' '.join([get_text(p) for p in description_pars])
        description = pre_description.strip()
        print('Append description:', description[0:30]+'..')
        return 'append', None, description

    # extract title_el form DOM
    title_el.extract()

    pre_description = ' '.join([p.get_text().replace('\n',' ').strip() for p in description_pars])
    description = pre_description.strip()
    return 'new', title, description





def process_language_page(lang, page_url):
    """
    Process a top-level collection page for a given language.
    """
    page = get_parsed_html_from_url(page_url)

    web_resource_tree = dict(
        kind='TessaLangWebRessourceTree',
        title='TESSA (%s)' % lang.upper(),
        url=page_url,
        lang=lang,
        children=[],
    )

    pre_activity_links = page.find(class_="course-content").find_all("li", class_="activity")
    activity_links = list(pre_activity_links)
    print('\n\n')
    print('Processing TESSA page ', lang.upper(), '    num of unfiltered activity links:', len(activity_links))


    finished_with_modules = False
    current_category = None
    for activity in activity_links:
        # print(activity.text[0:50])
        activity_type = get_modtype(activity)

        # HEADINGS AND DESCRIPTIONS
        if activity_type in ['label', 'heading']:

            # Recognize when done with modules and starting "Additional resources" section
            activity_title = get_text(activity)
            if activity_title in ADDITIONAL_RESOURCES_TITLES:
                finished_with_modules = True

            # special handling for first list item--conatins ah-hoc formatted channel specific info
            if current_category is None and activity_type == 'label':
                channel_description = extract_channel_description(activity)
                web_resource_tree['description'] = channel_description
                current_category = {'title':'Something not-None that will be overwritten very soon...',
                                    'description':'',
                                    'children':[]}
                continue

            # skip last footer section
            home_link = activity.select('a[href="' + TESSA_HOME_URL + '"]')
            if home_link:
                print('Skipping footer section....')
                continue

            action, title, description = extract_category_from_modtype_label(activity)
            if action == 'new':
                new_category = dict(
                    kind='TessaCategory',
                    source_id='category_' + title.replace(' ', '_'),
                    title=title,
                    lang=lang,
                    description='',  # description, #        # Sept13hack
                    children = [],
                )
                web_resource_tree['children'].append(new_category)
                current_category = new_category
            elif action == 'append':
                current_category['description'] += ' ' + description   # TODO: add \n\n
            else:
                raise ValueError('Uknown action encountered:' + str(action) )

        # MODULE SUBPAGES
        elif activity_type == 'subpage' and finished_with_modules == False:
            info_dict = get_resource_info(activity)
            print('\n\nAdding subpage', info_dict['title'])
            subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=page_url)
            # print(info_dict)
            current_category['children'].append(subpage_node)


        # ADDITIONAL RESOURCES SUBPAGES
        elif activity_type == 'subpage' and finished_with_modules:
            info_dict = get_resource_info(activity)
            print('\n\nFound ADDITIONAL RESOURCES SUBPAGE', info_dict['title'])
            # TODO: remove one folder-deep, process title and description  :TODO:  :TODO:  :TODO:  :TODO:
            subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=page_url)
            # print(subpage_node)
            current_category['children'].append(subpage_node)


        # SPECIAL HANDLING FOR NON SUBPAGE CONTENT NODES
        elif activity_type == 'oucontent':
            outcontent_dict = get_resource_info(activity)
            print('Adding oucontent', outcontent_dict['title'])
            del outcontent_dict['type']
            outcontent_dict['kind'] = 'TessaContentPage'
            outcontent_dict['lang'] = lang
            current_category['children'].append(outcontent_dict)

        # ALSO TAKE PDF RESOURCES
        elif activity_type == 'resource':
            info_dict = get_resource_info(activity)
            if 'pdf' in info_dict['title']:
                current_category['children'].append(info_dict)
            else:
                print('Ignoring activity of type', activity_type, '\tstartswith:',
                      activity.get_text()[0:50].replace('\n',' '))


        # REJECT EVERYTHING ELSE
        else:
            print('Ignoring activity of type', activity_type, '\tstartswith:',
                  activity.get_text()[0:50].replace('\n',' '))

    return web_resource_tree



def create_subpage_node(subpage_dict, lang=None, lang_main_menu_url=None):
    """
    Parse `TessaSubpage`-type objects linked to from the main language page.
    """
    url = subpage_dict["url"]
    print(url)
    topic_id = url_to_id(url)
    if not topic_id:
        print('ERROR: could not find topic_id in create_subpage_node')
        return
    topic_id = topic_id[0]


    subpage_node = dict(
        kind='TessaSubpage',
        url=url,
        source_id="topic_%s" % topic_id,
        title=subpage_dict["title"],
        lang=lang,
        description='', # TODO add descriptions for subpages....',
        children=[],
    )
    # print('    subpage_node: ' + str(subpage_node))

    # let's go get subpage contents...
    subpage = get_parsed_html_from_url(url)

    course_content = subpage.find('div', class_='course-content')
    topics_ul = course_content.find('ul', class_='topics')
    section_lis = topics_ul.find_all('li', class_="section")
    # print('len(section_lis) = ', len(section_lis)    )


    # CASE A: STANDARD MODULE
    if len(section_lis) > 1:
        # Some modules are conained in a div.course-content > ul.topics > li.section > (title in h3)
        for section_li in section_lis:

            module_heading_el = section_li.find('h3', class_="sectionname")
            if module_heading_el is None:
                module_heading_el = section_li.find('h4')  # fallback for headings as h4

            # skip solo footer sections
            if module_heading_el is None and section_li.select('a[href="' + TESSA_HOME_URL + '"]'):
                continue

            if module_heading_el:
                module_title = get_text(module_heading_el)
                # COMBINED?
                content_items = section_li.find_all("li", class_="modtype_oucontent")
                resource_items = section_li.find_all("li", class_="modtype_resource")
                if content_items and resource_items:
                    print('FOUND   content_items and resource_items: >>>>>>>>>>>>>>>>>>>>>>')

                # STANDARD MODULES
                content_items = section_li.find_all("li", class_="modtype_oucontent")
                if content_items:
                    first, rest = content_items[0], content_items[1:]
                    li_module_info = get_resource_info(first)
                    print(' - Recognizd standard module structure. Taking whole module:')
                    print('   Content (%s):' % li_module_info['type'], li_module_info['title'])
                    del li_module_info['type']
                    li_module_info['kind'] = 'TessaModule'
                    li_module_info['lang'] = lang
                    subpage_node['children'].append(li_module_info)
                    # for li in rest:
                    #     print('    - skipping module section li', li.get_text())
                    all_items = section_li.find_all("li")
                    other_items = [item for item in all_items if item not in content_items]
                    for other_item in other_items:
                        print('    - skipping other li', get_text(other_item)[0:40])


                # RESOURCES
                resource_items = section_li.find_all("li", class_="modtype_resource")
                if resource_items:
                    for resouce_item in resource_items:
                        resouce_dict = get_resource_info(resouce_item)
                        print('         Resource (%s):' % resouce_dict['type'], resouce_dict['title'])
                        subpage_node['children'].append(resouce_dict)

                    all_items = section_li.find_all("li")
                    other_items = [item for item in all_items if item not in resource_items]
                    for other_item in other_items:
                        print('            skipping other li', get_text(other_item)[0:40])

            else:
                print('       - No heading el found in section so skipping...', get_text(section_li)[0:20])



    # CASE B: NONSTANDARD MODULE
    elif len(section_lis) == 1:
        # Other modules have > div.course-content
        #                       > ul.topics
        #                           > li.section [a single one]
        #                               > div.content
        #                                  > li.section
        # print(' - Nonstandard module, using fallback strategies...')
        outer_section_li = section_lis[0]
        content_div = outer_section_li.find('div', class_="content", recusive=False)
        activity_lis = content_div.find('ul', class_='section').find_all('li', class_="activity")

        # Check if first item is subpage description (if more than 100 chars)
        first_activity = activity_lis[0]
        first_activity_text = get_text(first_activity)
        if len(first_activity_text) >= 100:
            subpage_node['description'] = first_activity_text
            activity_lis = activity_lis[1:]
        else:
            subpage_node['description'] = ''

        # process list of items using state machine
        # START = take content items until you find a label
        # SKIPNEXTLABEL = skip next label item (to skip: Read or download individual sec...)
        # SKIP = skip content items until next label (to skip individual sections files)
        state = 'START'
        current_subject = None
        sections_skipped = 0
        for activity_li in activity_lis:

            activity_type = get_modtype(activity_li)
            # print('Processing nonstandard activity_li (%s)' % activity_type, get_text(activity_li)[0:40])

            # skip back-to-menu links
            if activity_li.select('a[href="' + TESSA_HOME_URL + '"]'):
                # print('skipping TESSA_HOME_URL link activity')
                continue
            elif activity_li.select('a[href="' + lang_main_menu_url + '"]'):
                print('skipping lang_main_menu_url link-containing activity')   # this is not necessary since above will catch...
                continue

            # Main state-machine logic
            if state == 'START':
                if activity_type == 'label':
                    # beginning of a new subject
                    title = get_text(activity_li)
                    current_subject = dict(
                        kind='TessaSubject',
                        source_id=topic_id + ':' + title,
                        title=title,
                        children=[]
                    )
                    subpage_node['children'].append(current_subject)
                    state = 'SKIPNEXTLABEL'
                elif activity_type == 'oucontent':
                    print('should never be here >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
                    pass

            elif state == 'SKIPNEXTLABEL':
                if activity_type == 'label':
                    state = 'SKIP'
                elif activity_type == 'oucontent':
                    module_info = get_resource_info(activity_li)
                    print(' - NEW! Recognizd standard module structure. Taking whole module:')
                    print('   Content (%s):' % module_info['type'], module_info['title'])
                    del module_info['type']
                    module_info['kind'] = 'TessaModule'
                    module_info['lang'] = lang
                    current_subject['children'].append(module_info)
                elif activity_type == 'subpage':
                    info_dict = get_resource_info(activity_li)
                    print('ZZZZZZZ Adding subpage', info_dict['title'])
                    subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=lang_main_menu_url)
                    # print(info_dict)
                    current_subject['children'].append(subpage_node)

            elif state == 'SKIP':
                if activity_type == 'label':
                    # beginning of a new subject
                    title = get_text(activity_li)
                    current_subject = dict(
                        kind='TessaSubject',
                        source_id=topic_id + ':' + title,
                        title=title,
                        children=[]
                    )
                    subpage_node['children'].append(current_subject)
                    state = 'SKIPNEXTLABEL'
                    print('   total oucontent sections skipped in prev module =', sections_skipped)
                    sections_skipped = 0
                elif activity_type == 'oucontent':
                    # print('skipping section...')
                    sections_skipped += 1
                    continue

        # done processing NONSTANDARD MODULE
        print('   total oucontent sections skipped in prev module =', sections_skipped)

    else:
        print('Found third case')
        raise ValueError('found third case')


    return subpage_node










# SCRAPING
################################################################################

def get_section_filename(sec_url):
    sec_num = parse_qs(urlparse(sec_url).query)['section'][0]
    return 'section-' + sec_num.replace('.', '_') + '.html'


def make_request(url, *args, **kwargs):
    response = sess.get(url, *args, **kwargs)
    if response.status_code != 200:
        LOGGER.debug("NOT FOUND:", url)
    elif not response.from_cache:
        LOGGER.debug("NOT CACHED:", url)
    return response


def get_parsed_html_from_url(url, *args, **kwargs):
    html = make_request(url, *args, **kwargs).content
    return BeautifulSoup(html, "html.parser")


def make_fully_qualified_url(url):
    if url.startswith("//"):
        print('unexpecded // url', url)
        return "http:" + url
    if url.startswith("/"):
        print('unexpecded / url', url)
        return "http://www.open.edu" + url
    if not url.startswith("http"):
        print('unexpecded non-full url', url)
        return "http://www.open.edu/" + url
    return url



def download_module(module_url, lang=None):
    LOGGER.debug('Scrapring module @ url =', module_url)
    doc = get_parsed_html_from_url(module_url)
    source_id = parse_qs(urlparse(module_url).query)['id'][0]
    raw_title = doc.select_one("head title").text
    module_title = raw_title.replace('OLCreate:', '')\
            .replace('TESSA_ARABIC', '')\
            .replace('TESSA_Eng', '')\
            .replace('TESSA_Fr', '')\
            .strip()
    module_contents_dict = dict(
        kind='TessaModuleContentsDict',
        lang=lang,
        source_id=source_id,
        title=module_title,
        children=[],
    )

    # TRY TO CREATE MODULE TOC SIDEBAR MENU
    ############################################################################
    current_li_deep = doc.find('li', class_='oucontent-tree-current')

    # Sept 5th: special treatement for modules with no TOC in sidebar
    if current_li_deep is None:
        return download_module_no_toc(module_url, lang=lang)


    # CREATE MODULE TOC SIDEBAR MENU
    # July 28 HACK : infer module_toc_li  using marker on sublist-li
    ############################################################################
    destination = tempfile.mkdtemp()
    print('destination=', destination)
    # copy css/js/images from skel
    shutil.copytree('chefdata/templates/module_skel/styles', os.path.join(destination,'styles'))

    is_first_section = True
    module_toc_li = current_li_deep.find_parent('li', class_='item-section')
    # print(module_toc_li.prettify())
    # module_contents_div = module_toc_li.find('div', class_='oucontent-contents')
    outer_module_ul = module_toc_li.find('ul', class_='child-item-list', recursive=False)
    inner_module_ul = outer_module_ul.find('div', class_='oucontent-contents').find('ul', recursive=False)
    section_lis = inner_module_ul.find_all('li', recursive=False)
    print(len(section_lis))

    # DETECT IF SIMPLE MODULE (single page, so sections) OR COMPLEX MODULE (with sections)
    if len(section_lis) == 0:
        print('UNEXPECTED --------  len(section_lis) == 0')
        print(module_url, '<<< <<< '*6)
    if len(section_lis) == 1:
        is_simple_module = True
    else:
        is_simple_module = False

    # SIMPLE MODULES THAT CONSIST OF A SINGLE PAGE -- becomes index.html
    if  is_simple_module:
        section_li =  section_lis[0]
        # print('*'*120)
        # print(section_li.prettify())
        section_title_span = section_li.find('span', class_='oucontent-tree-item')
        section_title = get_text(section_title_span)
        print('Processing simple module:', section_title)
        section_dict = dict(
            kind='TessaModuleContentsSection',
            title=section_title,
            href=module_url,
            filename='index.html',  # TODO: figure out if this is necessary
            children=[],
        )
        # print('  section:', section_title)
        module_contents_dict['children'].append(section_dict)

        subsections_ul = section_li.find('ul', recursive=False)
        if subsections_ul:
            pass
            #print('found some subsections...')
        else:
            pass
            #print('no subsections <ul> found in this section')

        download_page(module_url, destination, 'index.html', lang)
    # /SIMPLE MODULE


    # COMPLEX MODULES WITH SECTIONS AND custom-made TOC in index.html
    else:
        for section_li in section_lis:

            if 'download individual sections' in get_text(section_li):  # TODO: AR, SW, FR
                print('skipping section "Read or download individual sections..." ')
                continue

            # print(section_li.prettify())
            # print('>'*80)
            section_title_span = section_li.find('span', class_='oucontent-tree-item')
            if section_title_span:
                if section_title_span.find('span', class_='current-title'):
                    section_href = module_url
                else:
                    section_a = section_title_span.find('a')
                    if section_a:
                        section_href = section_a['href']
                    else:
                        section_href = '#NOLINK' # for sections like "Top 20 ideas for teaching large classes"
            else:
                section_href = '#NOLINK' # for sections like "Read or download individual sections of the m..."

            # special case for first section --- since it doesn't save section in filename
            # manually call download_page with filename section_1.html with contents of current page
            if is_first_section:
                section_filename = 'section-1.html'
                is_first_section = False
            else:
                if '#NOLINK' not in section_href:
                    section_filename = get_section_filename(section_href)

            # accesshide_span = section_title_span.find('span', class_='accesshide')
            # if accesshide_span:
            #     accesshide_span.extract()
            # subsections_ul.extract()
            section_title = get_text(section_title_span)

            section_dict = dict(
                kind='TessaModuleContentsSection',
                title=section_title,
                href=section_href,
                filename=section_filename,
                children=[],
            )
            # print('  section:', section_title)
            module_contents_dict['children'].append(section_dict)


            subsections_ul = section_li.find('ul', recursive=False)
            if subsections_ul:
                subsection_lis = subsections_ul.find_all('li')
                for subsection_li in subsection_lis:
                    # print('<'*100)
                    # print(subsection_li)
                    #print('>>>>>')
                    #print(subsection_li.prettify())
                    subsection_link = subsection_li.find('a')
                    subsection_href = subsection_link['href']
                    subsection_filename = get_section_filename(subsection_href)
                    # subaccesshide_span = subsection_li.find('span', class_='accesshide')
                    # if subaccesshide_span:
                    #     subaccesshide_span.extract()
                    subsection_title = get_text(subsection_li)
                    subsection_dict = dict(
                        kind='TessaModuleContentsSubsection',
                        title=subsection_title,
                        href=subsection_href,
                        filename=subsection_filename,
                    )
                    # print('    subsection:', subsection_title)
                    section_dict['children'].append(subsection_dict)
            else:
                print('no subsections <ul> found in this section')

        module_index_tmpl = jinja2.Template(open('chefdata/templates/module_index.html').read())
        index_contents = module_index_tmpl.render(module=module_contents_dict)
        with open(os.path.join(destination, "index.html"), "w") as f:
            f.write(index_contents)

        # download the html content from each section/subsection
        for section in module_contents_dict['children']:
            if '#NOLINK' in section['href']:
                print('nothing to download for #NOLINK section')
                continue
            download_section(section['href'], destination, section['filename'], lang)
            for subsection in section['children']:
                if '#NOLINK' in subsection['href']:
                    print('nothing to download for #NOLINK subsection')
                    continue
                download_section(subsection['href'], destination, subsection['filename'], lang)
        # /COMPLEX MODULE

    zip_path = create_predictable_zip(destination)
    return zip_path



def _get_next_section_url(doc):
    # PARSE CURRENT PAGE
    wrapper_div = doc.find('div', class_="direction-btn-wrapper")
    if wrapper_div is None:
        print('wrapper_div is None')
        return None
    next_link = wrapper_div.find('a', class_="next")
    if next_link is None:
        # print('next_link is None')
        return None
    return next_link['href']


def download_module_no_toc(module_url, lang=None):
    """
    Extracting the module table of contents from the sidebad nav doesn't work for certain modules in FR
    e.g. http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=105334&section=1.1

    If NO TOC is available, then we'll crawl pages one by one
    (`module_contents_dict`)
    """
    LOGGER.debug('Scrapring module @ url =' + str(module_url))
    doc = get_parsed_html_from_url(module_url)
    destination = tempfile.mkdtemp()
    print('destination=', destination)

    # copy css/js/images from skel
    shutil.copytree('chefdata/templates/module_skel/styles', os.path.join(destination,'styles'))

    source_id = parse_qs(urlparse(module_url).query)['id'][0]
    raw_title = doc.select_one("head title").text
    module_title = raw_title.replace('OLCreate:', '')\
            .replace('TESSA_ARABIC', '')\
            .replace('TESSA_Eng', '')\
            .replace('TESSA_Fr', '')\
            .strip()

    module_contents_dict = dict(
        kind='TessaModuleContentsDict',
        source_id=source_id,
        title=module_title,
        lang=lang,
        children=[],
    )
    # print(module_contents_dict)

    # recusively download all sections by following "Next" links
    current_url = module_url
    current_section = None
    is_first_section = True
    while True:
        LOGGER.debug('processing current_url' + str(current_url))
        current_doc = get_parsed_html_from_url(current_url)


        # special handling for module-level page (no section in url but is really Section 1)
        if is_first_section:
            section_filename = 'section-1.html'
            is_first_section = False
        else:
            section_filename = get_section_filename(current_url)


        # Do the actual download
        download_section(current_url, destination, section_filename, lang)


        # Store section/subsecito info so we can build TOC later
        doc = get_parsed_html_from_url(current_url)
        raw_title = doc.select_one("head title").text
        the_title = raw_title.replace('OLCreate:', '')\
                .replace('TESSA_ARABIC', '')\
                .replace('TESSA_Eng', '')\
                .replace('TESSA_Fr', '')\
                .strip()

        # sections e.g. section-3.html
        if '_' not in section_filename:
            section_dict = dict(
                kind='TessaModuleContentsSection',
                title=the_title,
                href=current_url,
                filename=section_filename,
                children=[]
            )
            module_contents_dict['children'].append(section_dict)
            print('  - section:', the_title[0:80])
            current_section = section_dict

        # subsections e.g. section-3_2.html
        else:
            subsection_title = the_title.replace(module_title,'')
            subsection_title.replace(current_section['title'],'')
            subsection_title = subsection_title.lstrip()
            if subsection_title.startswith(': '):
                subsection_title = subsection_title.replace(': ', '', 1)
            subsection_dict = dict(
                kind='TessaModuleContentsSubsection',
                title=subsection_title,
                href=current_url,
                filename=section_filename,
            )
            print('     - subsection:', subsection_title[0:80])
            current_section['children'].append(subsection_dict)


        # Recurse if next
        next_url = _get_next_section_url(current_doc)
        if next_url:
            current_url = next_url
        else:
            break

    # for debugging...
    # pp.pprint(module_contents_dict)

    module_index_tmpl = jinja2.Template(open('chefdata/templates/module_index.html').read())
    index_contents = module_index_tmpl.render(module=module_contents_dict)
    with open(os.path.join(destination, "index.html"), "w") as f:
        f.write(index_contents)

    # return module_contents_dict
    zip_path = create_predictable_zip(destination)
    return zip_path




def scrape_content_page(content_page_url, lang):
    """
    Download standalone HTML content pages (non-modules).
    Used for "Curriculum framework" and standalone pages in "Resources".
    Returns:
        page_info (dict):  info necessary to constructing HTML5AppNode and HTMLZipFile
          - title
          - source_id
          - description
          - zip_path
    """
    LOGGER.debug('Scrapring content page @ url =' + str(content_page_url))
    doc = get_parsed_html_from_url(content_page_url)

    destination = tempfile.mkdtemp()
    print('destination=', destination)

    source_id = parse_qs(urlparse(content_page_url).query)['id'][0]
    raw_title = doc.select_one("head title").text
    content_title = raw_title.replace('OLCreate:', '')\
            .replace('TESSA_ARABIC', '')\
            .replace('TESSA_Eng', '')\
            .replace('TESSA_Fr', '')\
            .strip()

    page_info = dict(
        lang=lang,
        source_id=source_id,
        title=content_title,
        description=None,
        children=[],
    )

    # Do the actual download
    download_page(content_page_url, destination, 'index.html', lang)

    # zip it
    page_info['zip_path'] = create_predictable_zip(destination)

    # ship it
    return page_info




def download_assets(doc, selector, attr, destination, middleware=None):
    """
    Find all assets in `attr` for DOM elements that match `selector` within doc
    and download them to `destination` dir.
    """
    nodes = doc.select(selector)
    for i, node in enumerate(nodes):
        url = make_fully_qualified_url(node[attr])
        filename = "%s_%s" % (i, os.path.basename(url))
        node[attr] = filename
        download_file(url, destination, request_fn=make_request, filename=filename, middleware_callbacks=middleware)


def js_middleware(content, url, **kwargs):
    return content


def download_section(page_url, destination, filename, lang):
    LOGGER.debug('Scrapring section/subsectino...', filename)
    doc = get_parsed_html_from_url(page_url)
    source_id = parse_qs(urlparse(page_url).query)['id'][0] + '/' + filename   # or should I use &section=1.6 ?

    # We're only interested in the main content inside the section#region-main
    main_region = dict(
        args=['section'],
        kwargs={'id': 'region-main'},
    )
    section = doc.find(*main_region['args'], **main_region['kwargs'])

    # CLEANUP
    course_details_header_div = section.find('div', class_='course-details-content-header')
    if course_details_header_div:
        course_details_header_div.extract()

    print_page_div = section.find('div', class_='print-page-section')
    if print_page_div:
        print_page_div.extract()

    copyright_info_div = section.find('div', class_='copyright-info-content')
    if copyright_info_div:
        copyright_info_div.extract()

    # Download all static assets
    download_assets(section, "img[src]", "src", destination)     # Images
    download_assets(section, "link[href]", "href", destination)  # CSS
    download_assets(section, "script[src]", "src", destination, middleware=js_middleware) # JS

    raw_title = doc.select_one("head title").text
    section_title = raw_title.replace('OLCreate:', '')\
            .replace('TESSA_ARABIC', '')\
            .replace('TESSA_Eng', '')\
            .replace('TESSA_Fr', '')\
            .strip()

    section_dict = dict(
        title=section_title,
        lang=lang,
        main_content=str(section),
    )

    section_index_tmpl = jinja2.Template(open('chefdata/templates/section_index.html').read())
    index_contents = section_index_tmpl.render(
        section = section_dict,
    )
    with open(os.path.join(destination, filename), "w") as f:
        f.write(index_contents)




def download_page(page_url, destination, filename, lang):
    LOGGER.debug('Scrapring page...', page_url)
    doc = get_parsed_html_from_url(page_url)
    source_id = parse_qs(urlparse(page_url).query)['id'][0] + '/' + filename   # or should I use &section=1.6 ?

    # We're only interested in the main content inside the section#region-main
    main_region = dict(
        args=['section'],
        kwargs={'id': 'region-main'},
    )
    section = doc.find(*main_region['args'], **main_region['kwargs'])

    # CLEANUP
    course_details_header_div = section.find('div', class_='course-details-content-header')
    if course_details_header_div:
        course_details_header_div.extract()

    print_page_div = section.find('div', class_='print-page-section')
    if print_page_div:
        print_page_div.extract()

    copyright_info_div = section.find('div', class_='copyright-info-content')
    if copyright_info_div:
        copyright_info_div.extract()

    # Download all static assets
    download_assets(section, "img[src]", "src", destination)     # Images
    download_assets(section, "link[href]", "href", destination)  # CSS
    download_assets(section, "script[src]", "src", destination, middleware=js_middleware) # JS

    raw_title = doc.select_one("head title").text
    page_title = raw_title.replace('OLCreate:', '')\
            .replace('TESSA_ARABIC', '')\
            .replace('TESSA_Eng', '')\
            .replace('TESSA_Fr', '')\
            .strip()

    page_dict = dict(
        title=page_title,
        lang=lang,
        main_content=str(section),
    )
    page_index_tmpl = jinja2.Template(open('chefdata/templates/content_page_index.html').read())
    index_contents = page_index_tmpl.render(
        page = page_dict,
    )
    with open(os.path.join(destination, filename), "w") as f:
        f.write(index_contents)





def _build_json_tree(parent_node, sourcetree, lang=None):
    # type: (dict, List[dict], str) -> None
    """
    Parse the web resource nodes given in `sourcetree` and add as children of `parent_node`.
    """
    # EXPECTED_NODE_TYPES = ['TessaLangWebRessourceTree', 'TessaCategory', 'TessaSubpage',
    #                        'TessaModule']
    for source_node in sourcetree:
        if 'kind' not in source_node:
            print('kind-less source_node', source_node)
            continue
        kind = source_node['kind']
        # if kind not in EXPECTED_NODE_TYPES:
        #     raise NotImplementedError('Unexpected web resource node type encountered.')

        if kind == 'TessaLangWebRessourceTree':
            # this is the root of the tree, no special attributes, just process children
            source_tree_children = source_node.get("children", [])
            _build_json_tree(parent_node, source_tree_children, lang=lang)

        elif kind == 'TessaCategory':
            child_node = dict(
                kind='TopicNode',
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description='', # TODO description of ' + source_node['title'],
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            logger.debug('Created new TopicNode for TessaSubpage titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaSubpage':
            child_node = dict(
                kind='TopicNode',
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description='', # 'TODO description of ' + source_node['url'],
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            logger.debug('Created new TopicNode for TessaSubpage titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaSubject':
            description = source_node.get('description', None)
            child_node = dict(
                kind='TopicNode',
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description=description,
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            logger.debug('Created new TopicNode for TessaSubject titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaModule':
            child_node = dict(
                kind='HTML5AppNode',
                source_id=source_node['source_id'],
                # language=source_node['lang'],  # node-level language is not supported yet...
                title=source_node['title'],
                description='', # 'fake descri', # TODO source_node['description']
                files=[],
            )
            zip_path = download_module(source_node['url'], lang=source_node['lang'])
            module_html_file = dict(
                file_type='HTMLZipFile',
                path=zip_path,
                language=source_node['lang'],
            )
            child_node['files'] = [module_html_file]
            parent_node['children'].append(child_node)
            logger.debug('Created HTML5AppNode for TessaModule titled ' + child_node['title'])

        elif kind == 'TessaContentPage':
            page_info = scrape_content_page(source_node['url'], lang)
            child_node = dict(
                kind='HTML5AppNode',
                source_id=source_node['source_id'],
                # language=source_node['lang'],  # node-level language is not supported yet...
                title=source_node['title'],
                description=source_node.get('description', ''),
                files=[],
            )
            module_html_file = dict(
                file_type='HTMLZipFile',
                path=page_info['zip_path'],
                language=source_node['lang'],
            )
            child_node['files'] = [module_html_file]
            parent_node['children'].append(child_node)
            logger.debug('Created HTML5AppNode for TessaContentPage titled ' + child_node['title'])

        else:
            # logger.critical("Encountered an unknown content node format.")
            print('Skipping content kind', source_node['kind'], 'titled', source_node['title'])
            continue

    return parent_node



def scraping_part(args, options):
    """
    Download all categories, subpages, modules, and resources from open.edu.
    """
    lang = options['lang']
    # Read web_resource_trees.json
    with open(os.path.join(TREES_DATA_DIR, CRAWLING_STAGE_OUTPUT_TPL.format(lang))) as json_file:
        web_resource_tree = json.load(json_file)
        assert web_resource_tree['kind'] == 'TessaLangWebRessourceTree'

    # Ricecooker tree
    ricecooker_json_tree = dict(
        # kind='USEDTOBEChannelNode',
        # source_domain=web_resource_tree['source_domain'],
        # source_id=web_resource_tree['source_id'] + source_id_suffix,
        # title=web_resource_tree['title'] + source_id_suffix,
        # thumbnail=web_resource_tree['thumbnail'],
        language=web_resource_tree['lang'],
        children=[],
    )
    _build_json_tree(ricecooker_json_tree, web_resource_tree['children'], lang=options['lang'])
    print('finished building ricecooker_json_tree')

    # Write out ricecooker_json_tree.json
    json_file_name = os.path.join(TREES_DATA_DIR, SCRAPING_STAGE_OUTPUT_TPL.format(lang))
    with open(json_file_name, 'w') as json_file:
        json.dump(ricecooker_json_tree, json_file, indent=2)
        logger.info('Intermediate result stored in ' + json_file_name)
    logger.info('Scraping part finished.\n')





# CHEF
################################################################################

def build_tree_for_language(parent_node, sourcetree):
    """
    Parse nodes given in `sourcetree` and add as children of `parent_node`.
    """
    EXPECTED_NODE_TYPES = ['TopicNode', 'AudioNode', 'DocumentNode', 'HTML5AppNode']

    for source_node in sourcetree:
        kind = source_node['kind']
        if kind not in EXPECTED_NODE_TYPES:
            logger.critical('Unexpected Node type found: ' + kind)
            raise NotImplementedError('Unexpected Node type found in channel json.')

        if kind == 'TopicNode':
            child_node = nodes.TopicNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            parent_node.add_child(child_node)
            source_tree_children = source_node.get("children", [])
            build_tree_for_language(child_node, source_tree_children)

        elif kind == 'AudioNode':
            child_node = nodes.AudioNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                # derive_thumbnail=True,                    # video-specific data
                thumbnail=source_node.get('thumbnail'),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        elif kind == 'DocumentNode':
            child_node = nodes.DocumentNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        elif kind == 'HTML5AppNode':
            child_node = nodes.HTML5AppNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        else:
            logger.critical("Encountered an unknown content node format.")
            continue

    return parent_node

def add_files(node, file_list):
    EXPECTED_FILE_TYPES = ['VideoFile', 'ThumbnailFile', 'HTMLZipFile', 'DocumentFile']

    for f in file_list:

        file_type = f.get('file_type')
        if file_type not in EXPECTED_FILE_TYPES:
            logger.critical(file_type)
            raise NotImplementedError('Unexpected File type found in channel json.')

        path = f.get('path')  # usually a URL, not a local path

        # handle different types of files
        if file_type == 'VideoFile':
            node.add_file(files.VideoFile(path=f['path'], ffmpeg_settings=f.get('ffmpeg_settings')))
        elif file_type == 'ThumbnailFile':
            node.add_file(files.ThumbnailFile(path=path))
        elif file_type == 'HTMLZipFile':
            node.add_file(files.HTMLZipFile(path=path, language=f.get('language')))
        elif file_type == 'DocumentFile':
            node.add_file(files.DocumentFile(path=path, language=f.get('language')))
        else:
            raise UnknownFileTypeError("Unrecognized file type '{0}'".format(f['path']))




# CHEF
################################################################################

class TessaChef(SushiChef):
    """
    This class takes care of downloading content from tessafrica.net and uplaoding
    it to the Kolibri content curation server.
    This chef depends on the option `lang` being passed on the command line.
    """
    language_url_map = {
        'en': 'http://www.open.edu/openlearncreate/course/view.php?id=2042',
        'fr': 'http://www.open.edu/openlearnworks/course/view.php?id=2046',
        'ar': 'http://www.open.edu/openlearnworks/course/view.php?id=2198',
        'sw': 'http://www.open.edu/openlearnworks/course/view.php?id=2199',
    }


    def crawl(self, args, options):
        """
        PART 1: CRAWLING
        Builds the json web redource tree --- the recipe of what is to be downloaded.
        """
        if 'lang' not in options:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = options['lang']
        if lang == 'all':
            langs_to_crawl = ['en', 'fr', 'ar', 'sw']
        else:
            langs_to_crawl = [lang]

        for lang in langs_to_crawl:
            # 1. crawl
            top_level_url = TESSA_LANG_URL_MAP[lang]
            print('\n\n\n')
            print('crawling lang=', lang, 'starting at', top_level_url)
            web_resource_tree = process_language_page(lang, top_level_url)

            # 2. save unfiltered data to chefdata/trees/
            file_name_tpl = CRAWLING_STAGE_OUTPUT_TPL.replace('.json', '_unfiltered.json')
            json_file_name = os.path.join(TREES_DATA_DIR, file_name_tpl.format(lang))
            with open(json_file_name, 'w') as json_file:
                json.dump(web_resource_tree, json_file, indent=2)
                print('Unfiltered result stored in ' + json_file_name)

            # 3. call filter_unwanted_categories and save filtered
            # filtered_wrt = filter_unwanted_categories(web_resource_tree)  # Disable so we scrape all
            filtered_wrt = web_resource_tree
            json_file_name = os.path.join(TREES_DATA_DIR, CRAWLING_STAGE_OUTPUT_TPL.format(lang))
            with open(json_file_name, 'w') as json_file:
                json.dump(filtered_wrt, json_file, indent=2)
                print('Filtered result stored in ' + json_file_name)


    def scrape(self, args, options):
        """
        Call main function for PART 2: SCRAPING.
        """
        if 'lang' not in options:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        scraping_part(args, options)


    def pre_run(self, args, options):
        """
        Run the preliminary parts:
          - creawl the TESSA content site (open.edu) and build a web resource
            tree (see result in `chefdata/trees/web_resource_trees.json`)
          - scrape content and links from video lessons to build the json tree
            of the channel (see result in `chefdata/ricecooker_json_tree.json`)
          - perform manual content fixes for video lessons with non-standard markup
        """
        self.crawl(args, options)
        self.scrape(args, options)

    def run(self, args, options):
        self.pre_run(args, options)
        print('skipping rest of run because want to debug quickly...')

    def get_channel(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        channel = ChannelNode(
            source_domain = 'tessafrica.net',
            source_id = 'TESSA_%s-testing' % lang,         # TODO: remove -testing
            title = 'TESSA (%s)-testing' % lang.upper(),   # TODO: remove -testing
            thumbnail = 'http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png',
            description = 'Teacher Education in Sub-Saharan Africa, TESSA, is a collaborative network to help you improve your practice as a teacher or teacher educator. We provide free, quality resources that support your national curriculum and can help you plan lessons that engage, involve and inspire.',
            language = lang
        )
        return channel


    def construct_channel(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        channel = self.get_channel(**kwargs)
        # Load ricecooker json tree data for language `lang`
        with open(os.path.join(TREES_DATA_DIR, SCRAPING_STAGE_OUTPUT_TPL.format(lang))) as infile:
            lang_json_tree = json.load(infile)
            # lang_json_tree = None
            # json_trees = json.load(infile)
            # print(len(json_trees))
            # for tree in json_trees:
            #     print(tree)
            #     if tree['language'] == lang:
            #         lang_json_tree = tree
        if lang_json_tree is None:
            raise ValueError('Could not find ricecooker json tree for lang=%s' % lang)
        build_tree_for_language(channel, lang_json_tree['children'])
        raise_for_invalid_channel(channel)
        return channel




if __name__ == '__main__':
    tessa_chef = TessaChef()
    args, options = tessa_chef.parse_args_and_options()
    if 'lang' not in options:
        raise ValueError('Need to specify command line option `lang=XY`, where XY in en, fr, ar, sw.')
    tessa_chef.main()

