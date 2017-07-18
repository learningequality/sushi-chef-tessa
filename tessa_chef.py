#!/usr/bin/env python

from collections import defaultdict
import logging
import os
import re
import tempfile
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
import requests

from le_utils.constants import content_kinds, file_formats, licenses
from ricecooker.chefs import SushiChef
from ricecooker.classes.files import HTMLZipFile
from ricecooker.classes.licenses import get_license
from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, TopicNode
from ricecooker.config import LOGGER
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip


# Chef settings
################################################################################
DATA_DIR = 'chefdata'

CRAWLING_STAGE_OUTPUT = 'web_resource_trees.json'
SCRAPING_STAGE_OUTPUT = 'ricecooker_json_trees.json'

ZIP_FILES_TMP_DIR = os.path.join(DATA_DIR, 'zipfiles')


TESSA_LANG_URL_MAP = {
    'en': 'http://www.open.edu/openlearncreate/course/view.php?id=2042',
    'fr': 'http://www.open.edu/openlearnworks/course/view.php?id=2046',
    'ar': 'http://www.open.edu/openlearnworks/course/view.php?id=2198',
    'sw': 'http://www.open.edu/openlearnworks/course/view.php?id=2199',
}
TESSA_HOME_URL = 'http://www.tessafrica.net/home'


TESSA_STRINGS = {
    'en': {
        'module': 'Module',
        'key resource': 'Key Resource',
    }
}



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






# CRAWLING
################################################################################

# Looks at the top nav to get the current page subsection.
get_page_id = lambda p: get_text(p.find(id="page-navbar").find_all("span", itemprop='title')[-1])
get_text = lambda x: "" if x is None else x.get_text().replace('\n', ' ').strip()
# Used for modules that do not correspond to a single page ID.
get_key = lambda s: s.replace(" ", "_").replace("-","_").lower()
# Used for nodes that correspond to a single page (topics, sections).
url_to_id = lambda u: parse_qs(urlparse(u).query).get('id', '')


ALL_HIDDEN_SUBSPANS = set()


def get_modtype(activity):
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
        print(item)
        print('did not find link so returning None')
        return None

    title_span = item.find('span', class_="instancename")
    hidden_subspan = title_span.find("span", class_="accesshide")

    if hidden_subspan:
        hidden_subspan_text = hidden_subspan.get_text().replace('\n', ' ').strip()
        ALL_HIDDEN_SUBSPANS.add(hidden_subspan_text)
        hidden_subspan.extract()    # remove resouce type indicaton
    else:
        hidden_subspan_text = None

    title = title_span.get_text().replace('\n',' ').strip()
    return {
        "url": link["href"],
        "type": get_modtype(item),
        "title": title,
        'hidden_subspan_text': hidden_subspan_text,
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
                title_el = title_b
                # print('Bold title:', title)
                break

    if title_el is None:
        pre_description = ' '.join([p.get_text().replace('\n',' ').strip() for p in description_pars])
        description = pre_description.strip()
        print('Append description:', description[0:30]+'..')
        return 'append', None, description


    # extract title_el form DOM
    title_el.extract()

    pre_description = ' '.join([p.get_text().replace('\n',' ').strip() for p in description_pars])
    description = pre_description.strip()
    return 'new', title, description





def process_language_page(lang, page):
    """
    Process a top-level collection page for a given language.
    """
    web_resource_tree = dict(
        title='TESSA (%s)' % lang.upper(),
        children=[],
    )

    pre_activity_links = page.find(class_="course-content").find_all("li", class_="activity")
    activity_links = list(pre_activity_links)
    print('\n\n')
    print('Processing TESSA page ', lang.upper(), 'Number of unfiltered activity links:', len(activity_links))

    current_category = None
    for activity in activity_links:
        # print(activity.text[0:50])
        activity_type = get_modtype(activity)

        # HEADINGS AND DESCRIPTIONS
        if activity_type in ['label', 'heading']:

            # special handling for first list item--conatins ah-hoc formatted channel specific info
            if current_category is None and activity_type == 'label':
                channel_description = extract_channel_description(activity)
                web_resource_tree['description'] = channel_description
                current_category = {'title':'Something not-None that will be overwritten very soon...'}
                continue

            # skip last footer section
            home_link = activity.select('a[href="' + TESSA_HOME_URL + '"]')
            if home_link:
                continue

            action, title, description = extract_category_from_modtype_label(activity)
            if action == 'new':
                new_category = dict(
                    title=title,
                    description=description,
                    children = [],
                )
                web_resource_tree['children'].append(new_category)
                current_category = new_category
            elif action == 'append':
                current_category['description'] += ' ' + description   # TODO: add \n\n
            else:
                raise ValueError('Uknown action encountered:' + str(action) )

        # SPECIAL HANDLING FOR NON SUBPAGE CONTENT NODES
        elif activity_type == 'oucontent':
            info_dict = get_resource_info(activity)

        # SUBPAGES
        elif activity_type == 'subpage':
            info_dict = get_resource_info(activity)
            subpage_node = create_subpage_node(info_dict)
            # print(info_dict)
            current_category['children'].append(subpage_node)

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












def split_subpage_list_by_label(subpage, subpage_node):
    """
    Fallback logic for Tessa subpages that do not consist of separate modules.
    Implements an ad-hock strategy for grouping content items (`li.activity`)
    into modules that contain content nodes.
    """
    pre_activity_links = subpage.find(class_="course-content").find_all("li", class_="activity")
    activity_links = list(pre_activity_links)
    print('         - ', 'Processing subpage', subpage_node['url'])
    print('           ', 'Number of activity links:', len(activity_links))


    def create_default_module(title, description, subpage_node):
        """
        If we encounter content item before a module has been created, we must
        create a "default" using the info from the subpage.
        """
        default_module = dict(
            type='TessaModule',
            title='FORCED::' + str(title) + 'maybe use ' + subpage_node['title'],
            description=description,
            children = [],
        )
        return default_module

    current_module = None
    for activity in activity_links:
        # print(activity.text[0:50])
        activity_type = get_modtype(activity)

        # HEADINGS AND DESCRIPTIONS
        if activity_type in ['label', 'heading']:

            # skip last footer section
            home_link = activity.select('a[href="' + TESSA_HOME_URL + '"]')
            if home_link:
                continue

            action, title, description = extract_category_from_modtype_label(activity)
            if action == 'new':
                new_module = dict(
                    type='TessaModule',
                    title=title,
                    description=description,
                    children = [],
                )
                subpage_node['children'].append(new_module)
                current_module = new_module
            elif action == 'append':
                if current_module:
                    current_module['description'] += ' ' + description   # TODO: add \n\n
                else:
                    new_module = create_default_module(title, description, subpage_node)
                    subpage_node['children'].append(new_module)
                    current_module = new_module
            else:
                raise ValueError('Uknown action encountered:' + str(action) )

        # SPECIAL HANDLING FOR NON SUBPAGE CONTENT NODES
        elif activity_type == 'oucontent':
            info_dict = get_resource_info(activity)
            if current_module:
                current_module['children'].append(info_dict)
            else:
                new_module = create_default_module('NO TITLE KNOWN', 'NO DESCRIPTION KNOWN', subpage_node)
                subpage_node['children'].append(new_module)
                current_module = new_module
                current_module['children'].append(info_dict)

        # SUBPAGES WITHIN SUBPAGES
        elif activity_type == 'subpage':
            print('           ', 'Encountered subpage within subpage #### RECUSING VIA create_subpage_node ##########')
            subsubpage_dict = get_resource_info(activity)
            subsubpage_node = create_subpage_node(subsubpage_dict)
            current_module['children'].append(subsubpage_node)

        # ALSO TAKE PDF RESOURCES
        elif activity_type == 'resource':
            info_dict = get_resource_info(activity)
            if 'pdf' in info_dict['title']:
                current_module['children'].append(info_dict)
            else:
                print('           ', 'Ignoring activity of type', activity_type, '\tstartswith:',
                      activity.get_text()[0:50].replace('\n',' '))


        # REJECT EVERYTHING ELSE
        else:
            print('           ', 'Ignoring activity of type', activity_type, '\tstartswith:',
                  activity.get_text()[0:50].replace('\n',' '))





def create_subpage_node(subpage_dict):
    print('\n\n')
    url = subpage_dict["url"]
    print(url)
    topic_id = url_to_id(url)
    if not topic_id:
        return
    topic_id = topic_id[0]


    subpage_node = dict(
        type='TessaSubpage',
        url=url,
        source_id="topic_%s" % topic_id,
        title=subpage_dict["title"],
        children=[],
    )
    # print('    subpage_node: ' + str(subpage_node))

    # let's go get subpage contents...
    r = sess.get(url)
    subpage = BeautifulSoup(r.content, "html5lib")


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
                    print('       - Recognizd standard module structure. Taking whole module:')
                    print('         Content (%s):' % li_module_info['type'], li_module_info['title'])
                    subpage_node['children'].append(li_module_info)
                    for li in rest:
                        print('            skipping module section li', li.get_text())
                    all_items = section_li.find_all("li")
                    other_items = [item for item in all_items if item not in content_items]
                    for other_item in other_items:
                        print('            skipping other li', get_text(other_item)[0:40])


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
        print('       - Nonstandard module, using fallback strategies...')
        outer_section_li = section_lis[0]
        content_div = outer_section_li.find('div', class_="content")
        activity_lis = content_div.find('ul', class_='section').find_all('li', class_="activity")
        for activity_li in activity_lis:
            activity_type = get_modtype(activity_li)
            print('         section_li (%s)' % activity_type, get_text(activity_li)[0:40])
            # resouce_dict = get_resource_info(resouce_item)
            # split_subpage_list_by_label(subpage, subpage_node)


    else:
        print
        print('Found third case')
        raise ValueError('found third case')


    return subpage_node




def create_content_node(content_dict):
    """
    Returns a `TessaContentWebResource` dictionary with the informaiton necessary
    for the scraping step.
    """
    source_id = url_to_id(content_dict['url'])
    if not source_id:
        return
    source_id = source_id[0]
    print('source_id', source_id)

    content_node = dict(
        type='TessaContentWebResource',
        url=content_dict['url'],
        source_id=source_id,
        title=content_dict['title'],
        description=content_dict.get('description'),
        # files=[HTMLZipFile(path=url)],
        license=licenses.CC_BY_SA
    )
    return content_node










# SCRAPING
################################################################################

def make_request(url, *args, **kwargs):
    response = sess.get(url, *args, **kwargs)
    if response.status_code != 200:
        print("NOT FOUND:", url)
    elif not response.from_cache:
        print("NOT CACHED:", url)
    return response


def get_parsed_html_from_url(url, *args, **kwargs):
    html = make_request(url, *args, **kwargs).content
    return BeautifulSoup(html, "html.parser")


def make_fully_qualified_url(url):
    if url.startswith("//"):
        return "http:" + url
    if url.startswith("/"):
        return "http://www.africanstorybook.org" + url  # TODO: fix or adjust
    if not url.startswith("http"):
        return "http://www.africanstorybook.org/" + url # TODO: fix or adjust
    return url




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


    def get_channel_info(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        channel_info = {
            'CHANNEL_SOURCE_DOMAIN': 'tessafrica.net',
            'CHANNEL_SOURCE_ID': 'TESSA_%s-testing' % lang,         # TODO: remove -testing
            'CHANNEL_TITLE': 'TESSA (%s)-testing' % lang.upper(),   # TODO: remove -testing
            'CHANNEL_THUMBNAIL': 'http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png',
            'CHANNEL_DESCRIPTION': 'Teacher Education in Sub-Saharan Africa, TESSA, is a collaborative network to help you improve your practice as a teacher or teacher educator. We provide free, quality resources that support your national curriculum and can help you plan lessons that engage, involve and inspire.',
        }
        return channel_info


    def get_channel(self, **kwargs):
        channel_info = self.get_channel_info(**kwargs)
        channel = ChannelNode(
            source_domain = channel_info['CHANNEL_SOURCE_DOMAIN'],
            source_id = channel_info['CHANNEL_SOURCE_ID'],
            title = channel_info['CHANNEL_TITLE'],
            thumbnail = channel_info.get('CHANNEL_THUMBNAIL'),
            description = channel_info.get('CHANNEL_DESCRIPTION'),
        )
        return channel


    def construct_channel(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        channel = self.get_channel(**kwargs)
        lang = kwargs['lang']
        return self.build_tree_for_language(channel, lang)


    def build_tree_for_language(self, channel, language):
        if language not in self.language_url_map:
            print("Language not found")
            return

        top_level_url = self.language_url_map[language]
        top_level_page = sess.get(top_level_url)
        b = BeautifulSoup(top_level_page.content, "html5lib")
        page_id = get_page_id(b)
        subpages = {k:v for k,v in process_language_page(b).items() if any(x and x.get('type','') == 'Subpage' for x in v)}

        for topic, subpages in subpages.items():
            # Subject Resources
            LOGGER.info('topic:' + str(topic))
            topic_node = TopicNode(source_id=get_key(topic), title=topic)
            channel.add_child(topic_node)
            for subpage in subpages:
                create_subpage_node(topic_node, subpage)

        return channel



if __name__ == '__main__':
    tessa_chef = TessaChef()
    tessa_chef.main()

