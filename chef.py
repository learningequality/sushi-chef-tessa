import requests
import tempfile
from bs4 import BeautifulSoup

from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, DocumentNode
from ricecooker.classes.files import HTMLZipFile, DocumentFile, ThumbnailFile
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter

from le_utils.constants import licenses

from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip

def construct_channel(*args, **kwargs):

    channel = ChannelNode(
        source_domain="tessafrica.net",
        source_id="tessafrica-test",
        title="TessAfrica Test",
        thumbnail="http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png",
    )

    soup = BeautifulSoup(open('example_page.html').read())
    downloads = soup.find(id="downloads")
    # import ipdb; ipdb.set_trace()
    links = [a for a in downloads.find_all("a") if a['href'].endswith('html.zip') and a.find(class_="oucontent-title")]
    if not links:
        return channel

    title = links[0].find(class_="oucontent-title").text.lstrip().strip()
    url = links[0]['href']
    source_id = url.split('/')[-1].replace('.html.zip','')

    doc = HTML5AppNode(source_id=source_id, title=title, files=[HTMLZipFile(path=url)], license=licenses.CC_BY_SA)
    channel.add_child(doc)

    return channel

if __name__ == '__main__':
    construct_channel()
