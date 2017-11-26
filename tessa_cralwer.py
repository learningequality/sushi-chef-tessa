#!/usr/bin/env python

import argparse
import re
from urllib.parse import urljoin, urldefrag


from basiccrawler.crawler import BasicCrawler, LOGGER, logging
LOGGER.setLevel(logging.INFO)


TESSA_HOME_URL = 'http://www.tessafrica.net/home'   # content is not here though...
TESSA_LANG_URL_MAP = {
    'en': 'http://www.open.edu/openlearncreate/course/view.php?id=2042',
    'fr': 'http://www.open.edu/openlearncreate/course/view.php?id=2046',
    'ar': 'http://www.open.edu/openlearncreate/course/view.php?id=2198',
    'sw': 'http://www.open.edu/openlearncreate/course/view.php?id=2199',
}
SUBPAGE_RE = re.compile('.*mod/subpage/.*')
CONTENT_RE = re.compile('.*mod/oucontent/.*')
RESOURCE_RE = re.compile('.*mod/resource/.*')



# Helper Methods
################################################################################

def get_text(element):
    """
    Extract text contents of `element`, normalizing newlines to spaces and stripping.
    """
    if element is None:
        return ''
    else:
        return element.get_text().replace('\r', '').replace('\n', ' ').strip()


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
    resource_info =  {
        "url": link["href"],
        'source_id': source_id,
        "type": get_modtype(item),
        "title": title,
        'hidden_subspan_text': hidden_subspan_text,  # human-readbale equiv. of type
    }
    return resource_info




# CRAWLER
################################################################################

class TessaCrawler(BasicCrawler):
    """
    Crawler for the Teacher Education for Sub-Saharan Africa (TESSA) web resources
    hosted on open.edu/openlearncreate/ content management system.
    """
    MAIN_SOURCE_DOMAIN = 'http://www.open.edu'
    START_PAGE = None  # set in __init__
    START_PAGE_CONTEXT = {'kind':'TessaLangWebRessourceTree'}

    SOURCE_DOMAINS = ['http://www.tessafrica.net', 'http://www.open.edu', 'https://www.open.edu']
    IGNORE_URLS = [
        'http://www.open.edu/openlearn/',
        'http://www.open.edu/openlearncreate',
        'http://www.open.edu/openlearncreate/',
        'http://www.open.edu/openlearncreate/my/',
        'http://www.open.edu/openlearncreate/local/ocwactivityreports/',  # My profile
        'http://www.open.edu/openlearncreate/local/ocwcollections/collections.php',
        'http://www.open.edu/openlearncreate/course/index.php',
        'http://www.open.edu/openlearncreate/course/index.php?categoryid=25',   # all collections
        'http://www.open.edu/openlearncreate/course/index.php?categoryid=47',   # TESSA main page = parent for all langs
        'http://www.open.edu/openlearnworks/mod/url/view.php?id=83245',  # OLCreate: TESSA_SHARE TESSA - Share
        'http://www.open.edu/openlearncreate/local/ocwfaqs/faq.php',  # FAQ OpenLearn Create
    ]
    IGNORE_URL_PATTERNS = [
        re.compile('.*openlearncreate/login\.php.*'),
        re.compile('.*local/ocwcreatecourse/.*'),
        re.compile('.*local/ocwfreecourses/.*'),
        re.compile('.*mod/oucontent/olink.php.*'),  # weird kind of internal cross references (cause rescaping of things we alrady have)
        re.compile('.*oucontent/hidetip.php.*'),
    ]

    CRAWLING_STAGE_OUTPUT = 'chefdata/trees/web_resource_tree.json'




    def __init__(self, *args, lang='en', **kwargs):
        super().__init__(*args, **kwargs)
        self.START_PAGE = TESSA_LANG_URL_MAP[lang]
        self.START_PAGE_CONTEXT['lang'] = lang

        # save output for specific lang
        self.CRAWLING_STAGE_OUTPUT = self.CRAWLING_STAGE_OUTPUT.replace('.json', '_'+lang+'.json')

        # ignore main page links for other languages
        other_links = TESSA_LANG_URL_MAP.copy()
        del other_links[lang]
        self.IGNORE_URLS.extend(other_links.values())

        self.kind_handlers = {  # mapping from web resource kinds (user defined) and handlers
            'TessaLangWebRessourceTree': self.on_tessa_language_page,
            'subpage': self.on_subpage,
            'oucontent': self.on_oucontent,
            'resource': self.on_resource,
        }


    def cleanup_url(self, url):
        """
        Removes fragment and query string parameters that falsely make URLs look diffent.
        """
        url = urldefrag(url)[0]
        url = re.sub('&section=\d+(\.\d+)?', '', url)
        url = re.sub('&printable=1', '', url)
        url = re.sub('&content=scxml', '', url)
        url = re.sub('&notifyeditingon=1', '', url)
        url = re.sub(r'\?forcedownload=1', '', url)
        url = re.sub('&forcedownload=1', '', url)
        return url


    # PAGE HANDLERS
    ############################################################################

    def on_tessa_language_page(self, url, page, context):
        """
        Basic handler that adds current page to parent's children array and adds
        all links on current page to the crawling queue.
        """
        LOGGER.info('Procesing tessa_language_page ' + url)
        page_dict = dict(
            kind='TessaLangWebRessourceTree',
            url=url,
            title=self.get_title(page),
            children=[],
        )
        page_dict.update(context)

        # attach this page as another child in parent page
        context['parent']['children'].append(page_dict)

        course_content_div = page.find(class_="course-content")
        links = course_content_div.find_all('a')
        for i, link in enumerate(links):
            if link.has_attr('href'):
                link_url = urljoin(url, link['href'])
                link_title = get_text(link)
                if not self.should_ignore_url(link_url):
                    context = dict(
                        parent=page_dict,
                        title=link_title,
                    )
                    if SUBPAGE_RE.match(link_url):
                        context.update({'kind':'subpage'})
                        self.enqueue_url_and_context(link_url, context)
                    elif CONTENT_RE.match(link_url):
                        context.update({'kind':'oucontent'})
                        self.enqueue_url_and_context(link_url, context)
                    else:
                        LOGGER.debug('Skipping link ' + link_url + ' on page ' + url)
            else:
                pass
                # print(i, 'nohref', link)


    def on_subpage(self, url, page, context):
        LOGGER.info('Procesing subpage ' + url + ' title:' + context['title'])
        subpage_dict = dict(
            kind='TessaSubpage',
            url=url,
            children=[],
        )
        subpage_dict.update(context)

        # attach this page as another child in parent page
        context['parent']['children'].append(subpage_dict)

        course_content_div = page.find(class_="pagecontent-content")
        links = course_content_div.find_all('a')
        for i, link in enumerate(links):
            if link.has_attr('href'):
                link_url = urljoin(url, link['href'])
                link_title = get_text(link)
                if not self.should_ignore_url(link_url):
                    context = dict(
                        parent=subpage_dict,
                        title=link_title,
                    )
                    if SUBPAGE_RE.match(link_url):
                        context.update({'kind':'subpage'})
                        self.enqueue_url_and_context(link_url, context)
                    elif CONTENT_RE.match(link_url):
                        context.update({'kind':'oucontent'})
                        if 'Section' in link_title:
                            print('skipping secion...', link_title)
                            continue
                        self.enqueue_url_and_context(link_url, context)
                    elif RESOURCE_RE.match(link_url):
                        context.update({'kind':'resource'})
                        self.enqueue_url_and_context(link_url, context)
                    else:
                        LOGGER.debug(':::subpage::: Skipping link ' + link_url + ' ' + link_title)
            else:
                pass
                LOGGER.warning('a link with no href ' + str(link))


    def on_resources_subpage(self, url, page, context):
        LOGGER.info('Procesing resources_subpage ' + url + ' title:' + context['title'])
        subpage_dict = dict(
            kind='TessaResourcesSubpage',
            url=url,
            children=[],
        )
        subpage_dict.update(context)

        # attach this page as another child in parent page
        context['parent']['children'].append(subpage_dict)

        course_content_div = page.find(class_="pagecontent-content")


        course_content_div = page.find('div', class_="course-content")
        section_lis = course_content_div.find_all('li', class_="section")

        for section_li in section_lis:
            section_name = section_li.find(class_="sectionname")
            section_content_ul = section_li.find('ul', class_="section")
            activity_lis = section_content_ul.find_all('li', class_="activity")

            section_description = ''
            for activity_li in activity_lis:
                activity_type = get_modtype(activity_li)

                if activity_type in ['label', 'heading']:
                    section_description.append(activity_li.get_text())

                elif activity_type == 'resource':
                    link = activity_li.find_all('a')
                    link_url = urljoin(url, link['href'])
                    rsrc_info = get_resource_info(link)
                    context = dict(
                        parent=subpage_dict,
                        title=rsrc_info['title'],
                    )
                    context.update({'kind':'resource'})
                    self.enqueue_url_and_context(link_url, context)
                else:
                    LOGGER.debug(':::resources_subpage::: Skipping activity ' + str(activity_type) + ' ' + rsrc_info['title'])

        #
        #
        # links = course_content_div.find_all('a')
        # for i, link in enumerate(links):
        #     if link.has_attr('href'):
        #         link_url = urljoin(url, link['href'])
        #         link_title = get_text(link)
        #         if not self.should_ignore_url(link_url):
        #             context = dict(
        #                 parent=subpage_dict,
        #                 title=link_title,
        #             )
        #             if SUBPAGE_RE.match(link_url):
        #                 context.update({'kind':'subpage'})
        #                 self.enqueue_url_and_context(link_url, context)
        #             elif CONTENT_RE.match(link_url):
        #                 context.update({'kind':'oucontent'})
        #                 self.enqueue_url_and_context(link_url, context)
        #             elif RESOURCE_RE.match(link_url):
        #                 context.update({'kind':'resource'})
        #                 self.enqueue_url_and_context(link_url, context)
        #             else:
        #                 LOGGER.debug(':::subpage::: Skipping link ' + link_url + ' ' + link_title)
        #     else:
        #         pass
        #         LOGGER.warning('a link with no href ' + str(link))



    def on_oucontent(self, url, page, context):
        LOGGER.info('Procesing oucontent ' + url + ' title:' + context['title'])
        oucontent_dict = dict(
            kind='TessaContent',
            url=url,
            children=[],
        )
        oucontent_dict.update(context)

        # attach this page as another child in parent page
        context['parent']['children'].append(oucontent_dict)


    def on_resource(self, url, page, context):
        LOGGER.info('Procesing resource ' + url + ' title:' + context['title'])
        resource_dict = dict(
            kind='TessaResource',
            url=url,
            children=[],
        )
        resource_dict.update(context)

        # attach this resource as another child in parent page
        context['parent']['children'].append(resource_dict)

        pagecontent_div = page.find(class_="pagecontent-content")
        links = pagecontent_div.find_all('a')
        for i, link in enumerate(links):
            if link.has_attr('href'):
                link_url = urljoin(url, link['href'])
                link_title = get_text(link)
                if not self.should_ignore_url(link_url):
                    context = dict(
                        parent=resource_dict,
                        title=link_title,
                    )
                    self.enqueue_url_and_context(link_url, context)
            else:
                LOGGER.warning('a link with no href ' + str(link))



# CLI
################################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='This is the TESSA crawler')
    parser.add_argument('--lang', required=True, help='Which TESSA language to crawl')
    args = parser.parse_args()

    crawler = TessaCrawler(lang=args.lang)
    channel_tree = crawler.crawl(devmode=True, limit=10000)
    crawler.print_tree(channel_tree)
