#!/usr/bin/env python

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

from le_utils.constants import content_kinds, file_types, licenses
from ricecooker.chefs import JsonTreeChef
from ricecooker.classes.licenses import get_license
from ricecooker.config import LOGGER
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter
from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip

from tessa_cralwer import TessaCrawler



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
TESSA_LICENSE = get_license(licenses.CC_BY_NC_SA, copyright_holder='TESSA').as_dict()




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
LOGGER.setLevel(logging.DEBUG)



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



# CRAWLING
################################################################################
# see tessa_cralwer.py



# SCRAPING
################################################################################

def get_section_filename(sec_url):
    sec_num = parse_qs(urlparse(sec_url).query)['section'][0]
    return 'section-' + sec_num.replace('.', '_') + '.html'


def make_request(url, *args, **kwargs):
    response = sess.get(url, *args, **kwargs)
    if response.status_code != 200:
        LOGGER.debug("NOT FOUND:" + url)
    elif not response.from_cache:
        LOGGER.debug("NOT CACHED:" + url)
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
    LOGGER.debug('Scrapring module @ url =' + module_url)
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
                    if not subsection_link:  # handle wrird
                        LOGGER.warning('(((((  Skipping section ' + subsection_li.get_text() + ' because no subsection_link')
                        continue
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
    LOGGER.debug('Scrapring section/subsectino...' + filename)
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
    LOGGER.debug('Scrapring page...' + page_url)
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
                kind=content_kinds.TOPIC,
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description='', # TODO description of ' + source_node['title'],
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            LOGGER.debug('Created new TopicNode for TessaSubpage titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaSubpage':
            child_node = dict(
                kind=content_kinds.TOPIC,
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description='', # 'TODO description of ' + source_node['url'],
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            LOGGER.debug('Created new TopicNode for TessaSubpage titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaSubject':
            description = source_node.get('description', None)
            child_node = dict(
                kind=content_kinds.TOPIC,
                source_id=source_node['source_id'],
                title=source_node['title'],
                author='TESSA',
                description=description,
                thumbnail=source_node.get("thumbnail"),
                children=[],
            )
            parent_node['children'].append(child_node)
            LOGGER.debug('Created new TopicNode for TessaSubject titled ' + child_node['title'])
            source_tree_children = source_node.get("children", [])
            _build_json_tree(child_node, source_tree_children, lang=lang)

        elif kind == 'TessaModule':
            child_node = dict(
                kind=content_kinds.HTML5,
                source_id=source_node['source_id'],
                language=source_node['lang'],
                title=source_node['title'],
                description='', # 'fake descri', # TODO source_node['description']
                license=TESSA_LICENSE,
                files=[],
            )
            zip_path = download_module(source_node['url'], lang=source_node['lang'])
            module_html_file = dict(
                file_type=file_types.HTML5,
                path=zip_path,
                language=source_node['lang'],
            )
            child_node['files'] = [module_html_file]
            parent_node['children'].append(child_node)
            LOGGER.debug('Created HTML5AppNode for TessaModule titled ' + child_node['title'])

        elif kind == 'TessaContentPage':
            page_info = scrape_content_page(source_node['url'], lang)
            child_node = dict(
                kind=content_kinds.HTML5,
                source_id=source_node['source_id'],
                language=source_node['lang'],
                title=source_node['title'],
                description=source_node.get('description', ''),
                license=TESSA_LICENSE,
                files=[],
            )
            module_html_file = dict(
                file_type=file_types.HTML5,
                path=page_info['zip_path'],
                language=source_node['lang'],
            )
            child_node['files'] = [module_html_file]
            parent_node['children'].append(child_node)
            LOGGER.debug('Created HTML5AppNode for TessaContentPage titled ' + child_node['title'])

        elif kind == 'TessaAudioResoucePage':
            mp3_resource = source_node  # after refactor ... source_node['children'][0]
            child_node = dict(
                kind=content_kinds.AUDIO,
                source_id=source_node['source_id'],
                language=source_node['lang'],
                title=source_node['title'],
                description='', # 'fake descri', # TODO source_node['description']
                license=TESSA_LICENSE,
                files=[],
            )
            mp3_file = dict(
                file_type=file_types.AUDIO,
                path=mp3_resource['url'],
                language=source_node['lang'],
            )
            child_node['files'] = [mp3_file]
            parent_node['children'].append(child_node)
            LOGGER.debug('Created AudioNode from file url ' + mp3_resource['url'])

        elif kind == 'TessaPDFDocument':
            child_node = dict(
                kind=content_kinds.DOCUMENT,
                source_id=source_node['source_id'],
                language=source_node['lang'],
                title=source_node['title'],
                description='', # 'fake descri', # TODO source_node['description']
                license=TESSA_LICENSE,
                files=[],
            )
            pdf_file = dict(
                file_type=file_types.DOCUMENT,
                path=source_node['url'],
                language=source_node['lang'],
            )
            child_node['files'] = [pdf_file]
            parent_node['children'].append(child_node)
            LOGGER.debug('Created PDF Document Node from url ' + source_node['url'])

        else:
            # LOGGER.critical("Encountered an unknown content node format.")
            print('***** Skipping content kind', source_node['kind'], 'titled', source_node.get('title', 'NOTITLE') )
            continue

    return parent_node



def scraping_part(args, options):
    """
    Download all categories, subpages, modules, and resources from open.edu.
    """
    lang = options['lang']
    # Read web_resource_tree_{{lang}}.json
    with open(os.path.join(TREES_DATA_DIR, CRAWLING_STAGE_OUTPUT_TPL.format(lang))) as json_file:
        web_resource_tree = json.load(json_file)
        assert web_resource_tree['kind'] == 'TessaLangWebRessourceTree'

    # Ricecooker tree
    ricecooker_json_tree = dict(
        # kind='USEDTOBEChannelNode',
        source_domain=web_resource_tree['source_domain'],
        source_id=web_resource_tree['source_id'],
        title=web_resource_tree['title'],
        description=web_resource_tree['description'],
        thumbnail=web_resource_tree['thumbnail'],
        language=web_resource_tree['lang'],
        children=[],
        #
        # other non-essential attributes for
        url=web_resource_tree['url'],
    )
    _build_json_tree(ricecooker_json_tree, web_resource_tree['children'], lang=options['lang'])
    print('finished building ricecooker_json_tree')

    # Write out ricecooker_json_tree_{{lang}}.json
    json_file_name = os.path.join(TREES_DATA_DIR, SCRAPING_STAGE_OUTPUT_TPL.format(lang))
    with open(json_file_name, 'w') as json_file:
        json.dump(ricecooker_json_tree, json_file, indent=2)
        LOGGER.info('Intermediate result stored in ' + json_file_name)
    LOGGER.info('Scraping part finished.\n')








# CHEF
################################################################################

class TessaChef(JsonTreeChef):
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
            print('\n\n\n')
            print('crawling lang=', lang)
            crawler = TessaCrawler(lang=lang)
            web_resource_tree = crawler.crawl(devmode=True, limit=10000)

            # optional debug print...
            crawler.print_tree(web_resource_tree)



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
            tree (see result in `chefdata/trees/web_resource_tree_{{lang}}.json`)
          - scrape content and links from video lessons to build the json tree
            of the channel (see result in `chefdata/ricecooker_json_tree_{{lang}}.json`)
          - perform manual content fixes for video lessons with non-standard markup
        """
        self.crawl(args, options)
        # self.scrape(args, options)

    def run(self, args, options):
        self.pre_run(args, options)
        print('skipping rest of run because want to debug quickly...')


    def get_json_tree_path(self, **kwargs):
        """
        Return path to the ricecooker json tree file.
        Parent class `JsonTreeChef` implements get_channel and construct_channel
        that read their data from the json file specified by this function.
        Currently there is a single json file SCRAPING_STAGE_OUTPUT, but maybe in
        the future this function can point to different files depending on the
        kwarg `lang` (that's how it's done in several other mulitilingual chefs).
        """
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        json_tree_path = os.path.join(TREES_DATA_DIR, SCRAPING_STAGE_OUTPUT_TPL.format(lang))
        return json_tree_path




if __name__ == '__main__':
    tessa_chef = TessaChef()
    args, options = tessa_chef.parse_args_and_options()
    if 'lang' not in options:
        raise ValueError('Need to specify command line option `lang=XY`, where XY in en, fr, ar, sw.')
    tessa_chef.main()
