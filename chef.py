import itertools
import requests
from collections import defaultdict
from bs4 import BeautifulSoup
import urllib.parse as urlparse

from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, DocumentNode, TopicNode
from ricecooker.classes.files import HTMLZipFile, DocumentFile
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter

from le_utils.constants import licenses

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
        return channel

    url = links[0]['href']

    doc = HTML5AppNode(source_id=source_id, title=content_dict['title'], files=[HTMLZipFile(path=url)], license=licenses.CC_BY_SA)
    parent_node.add_child(doc)


def create_subpage_node(parent_node, subpage_dict):
    url = subpage_dict["url"]
    topic_id = url_to_id(url)
    if not topic_id:
        return
    topic_id = topic_id[0]
    # Life Skills
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
        topic.add_child(module)
        for activity in section.find_all("li", class_="modtype_oucontent"): 
            create_content_node(module, get_list_item(activity))


def create_channel_for_language(language, language_url_map):
    if language not in language_url_map:
        print("Language not found")
        return

    top_level_page = requests.get(language_url_map[language])
    b = BeautifulSoup(top_level_page.content, "html5lib")
    page_id = get_page_id(b)
    subpages = {k:v for k,v in split_list_by_label(b).items() if any(x and x.get('type','') == 'Subpage' for x in v)}

    channel = ChannelNode(
        source_domain="tessafrica.net",
        source_id=page_id,
        title="TessAfrica %s" % language,
        thumbnail="http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png",
    )

    for topic, subpages in subpages.items():
        # Subject Resources
        topic_node = TopicNode(source_id=get_key(topic), title=topic)
        channel.add_child(topic_node)
        for subpage in subpages:
            create_subpage_node(topic_node, subpage)

    return channel


def construct_channel(*args, **kwargs):

    language_url_map = {
        "en": "http://www.open.edu/openlearncreate/course/view.php?id=2042"
    }

    return create_channel_for_language("en", language_url_map)

if __name__ == '__main__':
    construct_channel()
