#!/usr/bin/env python

from collections import defaultdict
import logging
import os
import urllib.parse as urlparse

from bs4 import BeautifulSoup
import requests

from le_utils.constants import licenses
from ricecooker.chefs import SushiChef
from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, TopicNode
from ricecooker.classes.files import HTMLZipFile
from ricecooker.config import LOGGER
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.html import download_file



# Chef settings
################################################################################
DATA_DIR = 'chefdata'
ZIP_FILES_TMP_DIR = os.path.join(DATA_DIR, 'zipfiles')



TESSA_LANG_URL_MAP = {
    'en': 'http://www.open.edu/openlearncreate/course/view.php?id=2042',
    'fr': 'http://www.open.edu/openlearnworks/course/view.php?id=2046',
    'ar': 'http://www.open.edu/openlearnworks/course/view.php?id=2198',
    'sw': 'http://www.open.edu/openlearnworks/course/view.php?id=2199',
}
TESSA_HOME_URL = 'http://www.tessafrica.net/home'



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




# Looks at the top nav to get the current page subsection.
get_page_id = lambda p: get_text(p.find(id="page-navbar").find_all("span", itemprop='title')[-1])
get_text = lambda x: "" if x is None else x.text.lstrip().strip()
# Used for modules that do not correspond to a single page ID.
get_key = lambda s: s.replace(" ", "_").replace("-","_").lower()
# Used for nodes that correspond to a single page (topics, sections).
url_to_id = lambda u: urlparse.parse_qs(urlparse.urlparse(u).query).get('id', '')









def get_modtype(activity):
    classes = activity.get("class")
    for klass in classes:
        if klass.startswith('modtype_'):
            return klass.replace('modtype_', '')
    return None



def get_resource_info(item):
    link = item.find("a")
    if not link or not hasattr(link, "href") or not item.find("span", class_="accesshide"):
        print('did not find link so returning None')
        return None

    title_span = item.find('span', class_="instancename")
    hidden_subspan = title_span.find("span", class_="accesshide")
    hidden_subspan.extract()

    title = title_span.get_text().replace('\n',' ').strip()
    return {
        "url": link["href"],
        "type": get_modtype(item),
        "title": title,
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





def split_list_by_label(lang, page):
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

        # SPECIAL HANDLINE FOR NON SUBPAGE CONTENT NODES
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
        source_id="topic_%s" % topic_id,
        title=subpage_dict["title"],
        children=[],
    )
    # print('    subpage_node: ' + str(subpage_node))

    # let's go get subpage contents...
    r = sess.get(url)
    subpage = BeautifulSoup(r.content, "html5lib")


    course_content = subpage.find('div', class_='course-content')
    for section_li in course_content.find_all('li', class_="section"):

        # Some modules are conained in a div.course-content
        if section_li.find('h3', class_="sectionname"):
            module_title = get_text(section_li.find(class_="sectionname"))
            list_items = section_li.find_all("li", class_="modtype_oucontent")
            first, rest = list_items[0], list_items[1:]
            li_module_info = get_resource_info(first)
            print('         Content (%s):' % li_module_info['type'], li_module_info['title'][0:20]) #, li_module_info['url'][-3:])
            subpage_node['children'].append(li_module_info)
            for li in rest:
                pass
                # print(' skipping non-module li', li.get_text()[0:20])

        else:
            print('non standard module, using fallback strategies...')
            all_list_items = section_li.find('div', class_='content').find_all("li")
            print('number unfiltered items =', len(all_list_items))
            for item in all_list_items:
                item_dict = dict(
                    title=item.get_text().replace('\n',' ').strip()[0:40],
                    type='UNPARSED'
                )
                subpage_node['children'].append(item_dict)

    return subpage_node




def create_content_node(parent_node, content_dict):
    source_id = url_to_id(content_dict['url'])
    if not source_id:
        return
    source_id = source_id[0]

    r = sess.get(content_dict['url'])
    content_page = BeautifulSoup(r.content, 'html5lib')
    downloads = content_page.find(id="downloads")
    links = [a for a in downloads.find_all("a") if a['href'].endswith('html.zip') and a.find(class_="oucontent-title")]
    if not links:
        raise RuntimeError('No links found in create_content_node')

    url = links[0]['href']

    doc = HTML5AppNode(
        source_id=source_id,
        title=content_dict['title'],
        files=[HTMLZipFile(path=url)],
        license=licenses.CC_BY_SA
    )
    parent_node.add_child(doc)







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
        subpages = {k:v for k,v in split_list_by_label(b).items() if any(x and x.get('type','') == 'Subpage' for x in v)}

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

