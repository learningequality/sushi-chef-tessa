#!/usr/bin/env python

from bs4 import BeautifulSoup
from collections import defaultdict
import logging
import requests
import urllib.parse as urlparse


from le_utils.constants import licenses
from ricecooker.chefs import SushiChef
from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, TopicNode
from ricecooker.classes.files import HTMLZipFile
from ricecooker.config import LOGGER
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.html import download_file




# Set up webcaches.
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


def get_list_item(item):
    link = item.find("a")
    if not link or not hasattr(link, "href") or not item.find("span", class_="accesshide"):
        return

    return {
        "url": link["href"],
        "type": get_text(item.find("span", class_="accesshide")),
        "title": get_text(item).replace(get_text(item.find("span", class_="accesshide")), "").lstrip().strip()
    }


def split_list_by_label(page):
    links = defaultdict(list)
    all_links = page.find(class_="course-content").find_all("li", class_="activity")
    links_iter = all_links.__iter__()
    for activity in links_iter:
        if activity.find(class_="contentwithoutlink"):
            current_title = get_text(activity).replace('\n',' ')
            # throw away descriptions
            while activity.find(class_="contentwithoutlink"):
                try:
                    activity = links_iter.__next__()
                except StopIteration:
                    break
            links[current_title].append(get_list_item(activity))
        else:
            links[current_title].append(get_list_item(activity))
    return links


def create_content_node(parent_node, content_dict):
    source_id = url_to_id(content_dict['url'])
    if not source_id:
        return
    source_id = source_id[0]

    r = requests.get(content_dict['url'])
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


def create_subpage_node(parent_node, subpage_dict):
    url = subpage_dict["url"]
    topic_id = url_to_id(url)
    if not topic_id:
        return
    topic_id = topic_id[0]
    # Life Skills
    LOGGER.info('    subpage: ' + subpage_dict["title"])
    topic = TopicNode(source_id="topic_%s" % topic_id, title=subpage_dict["title"])
    parent_node.add_child(topic)
    r = requests.get(url)
    subpage = BeautifulSoup(r.content, "html5lib")
    for section in subpage.find_all(class_="section"):
        if not section.find(class_="sectionname"):
            continue
        module_name = get_text(section.find(class_="sectionname"))
        # Module 1: Personal Development
        module = TopicNode(source_id=get_key(module_name), title=module_name)
        LOGGER.info('       section: ' + module_name)
        topic.add_child(module)
        for activity in section.find_all("li", class_="modtype_oucontent"):
            LOGGER.info('          activity: ' + str(get_list_item(activity)['title']))
            create_content_node(module, get_list_item(activity))


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
            'CHANNEL_SOURCE_ID': 'tessa_africa_%s-testing' % lang,
            'CHANNEL_TITLE': 'TessAfrica (%s)' % lang.upper(),
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
        top_level_page = requests.get(top_level_url)
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

