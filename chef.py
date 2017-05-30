import requests
import tempfile
from bs4 import BeautifulSoup

from ricecooker.classes.nodes import ChannelNode, HTML5AppNode, TopicNode
from ricecooker.classes.files import HTMLZipFile, ThumbnailFile
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter

from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip

from ricecooker.classes import licenses

def construct_channel(*args, **kwargs):

    channel = ChannelNode(
        source_domain="tessafrica.net",
        source_id="tessafrica-test",
        title="TessAfrica Test",
        thumbnail="http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png",
    )

    citrus_topic = TopicNode(source_id="List_of_citrus_fruits", title="Citrus!")
    channel.add_child(citrus_topic)
    add_subpages_from_wikipedia_list(citrus_topic, "https://en.wikipedia.org/wiki/List_of_citrus_fruits")
    
    potato_topic = TopicNode(source_id="List_of_potato_cultivars", title="Potatoes!")
    channel.add_child(potato_topic)
    add_subpages_from_wikipedia_list(potato_topic, "https://en.wikipedia.org/wiki/List_of_potato_cultivars")

    return channel