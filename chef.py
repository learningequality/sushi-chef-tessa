import requests
from bs4 import BeautifulSoup

from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, DocumentNode
from ricecooker.classes.files import HTMLZipFile, DocumentFile
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter

from le_utils.constants import licenses

from ricecooker.utils.html import download_file

def create_channel_for_language(language, language_url_map):
    if language not in language_url_map:
        return

    try:
        top_level_page = requests.get(language_url_map[language])
    except:
        # TODO(arvind): log error
        return

    channel = ChannelNode(
        source_domain="tessafrica.net",
        source_id="tessafrica-test",
        title="TessAfrica Test",
        thumbnail="http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png",
    )

    soup = BeautifulSoup(open('example_page.html').read())
    downloads = soup.find(id="downloads")
    links = [a for a in downloads.find_all("a") if a['href'].endswith('html.zip') and a.find(class_="oucontent-title")]
    if not links:
        return channel

    title = links[0].find(class_="oucontent-title").text.lstrip().strip()
    url = links[0]['href']
    source_id = url.split('/')[-1].replace('.html.zip','')

    doc = HTML5AppNode(source_id=source_id, title=title, files=[HTMLZipFile(path=url)], license=licenses.CC_BY_SA)
    channel.add_child(doc)
    return channel


def construct_channel(*args, **kwargs):

    language_url_map = {
        "en": "http://www.open.edu/openlearncreate/course/view.php?id=2042"
    }

    return create_channel_for_language("en", languages)

if __name__ == '__main__':
    construct_channel()
