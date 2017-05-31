import itertools
import requests
from collections import defaultdict
from bs4 import BeautifulSoup

from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, DocumentNode
from ricecooker.classes.files import HTMLZipFile, DocumentFile
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter

from le_utils.constants import licenses

from ricecooker.utils.html import download_file

get_page_id = lambda p: p.find(id="page-navbar").find_all("span", itemprop='title')[-1].text.lstrip().strip()

def get_list_item(item):
    link = item.find("a")
    if not a or not hasattr(link, "href"):
        return

    return {
        "url": link["href"],
        "type": item.find("span", class_="accesshide").text.lstrip().strip(),
        "title": item.text.replace(item.find("span", class_="accesshide").text, "").lstrip().strip()
    }

def split_list_by_label(page):
    links = defaultdict(list)
    all_links = page.find(class_="course-content").find_all("li", class_="activity")
    links_iter = all_links.__iter__()
    for activity in links_iter:
        if activity.find(class_="contentwithoutlink"):
            current_title = activity.text.lstrip().strip()
            # throw away descriptions
            while activity.find(class_="contentwithoutlink"):
                activity = links_iter__.next__()
            links[current_title].append(get_list_item(activity))
        else:
            links[current_title].append(get_list_item(activity))
    return links


def create_channel_for_language(language, language_url_map):
    if language not in language_url_map:
        return

    try:
        top_level_page = requests.get(language_url_map[language])
        b = BeautifulSoup(r.content, "html5lib")
        page_id = get_page_id(b)
        content = split_list_by_label(b)
    except:
        # TODO(arvind): log error
        return

    channel = ChannelNode(
        source_domain="tessafrica.net",
        source_id=page_id,
        title="TessAfrica Test",
        thumbnail="http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png",
    )

    import ipdb; ipdb.set_trace()

    # soup = BeautifulSoup(open('example_page.html').read())
    # downloads = soup.find(id="downloads")
    # links = [a for a in downloads.find_all("a") if a['href'].endswith('html.zip') and a.find(class_="oucontent-title")]
    # if not links:
    #     return channel

    # title = links[0].find(class_="oucontent-title").text.lstrip().strip()
    # url = links[0]['href']
    # source_id = url.split('/')[-1].replace('.html.zip','')

    # doc = HTML5AppNode(source_id=source_id, title=title, files=[HTMLZipFile(path=url)], license=licenses.CC_BY_SA)
    # channel.add_child(doc)
    return channel


def construct_channel(*args, **kwargs):

    language_url_map = {
        "en": "http://www.open.edu/openlearncreate/course/view.php?id=2042"
    }

    return create_channel_for_language("en", languages)

if __name__ == '__main__':
    construct_channel()
