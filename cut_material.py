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






    def get_channel(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        channel = ChannelNode(
            source_domain = 'tessafrica.net',
            source_id = 'TESSA_%s-testing' % lang,         # TODO: remove -testing
            title = 'TESSA (%s)-testing' % lang.upper(),   # TODO: remove -testing
            thumbnail = 'http://www.tessafrica.net/sites/all/themes/tessafricav2/images/logotype_02.png',
            description = 'Teacher Education in Sub-Saharan Africa, TESSA, is a collaborative network to help you improve your practice as a teacher or teacher educator. We provide free, quality resources that support your national curriculum and can help you plan lessons that engage, involve and inspire.',
            language = lang
        )
        return channel


    def construct_channel(self, **kwargs):
        if 'lang' not in kwargs:
            raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ar, and sw.')
        lang = kwargs['lang']
        channel = self.get_channel(**kwargs)
        # Load ricecooker json tree data for language `lang`
        with open() as infile:
            lang_json_tree = json.load(infile)
            # lang_json_tree = None
            # json_trees = json.load(infile)
            # print(len(json_trees))
            # for tree in json_trees:
            #     print(tree)
            #     if tree['language'] == lang:
            #         lang_json_tree = tree
        if lang_json_tree is None:
            raise ValueError('Could not find ricecooker json tree for lang=%s' % lang)
        build_tree_for_language(channel, lang_json_tree['children'])
        raise_for_invalid_channel(channel)
        return channel





# Looks at the top nav to get the current page subsection.
get_page_id = lambda p: get_text(p.find(id="page-navbar").find_all("span", itemprop='title')[-1])

# Used for modules that do not correspond to a single page ID.
get_key = lambda s: s.replace(" ", "_").replace("-","_").lower()

# Used for nodes that correspond to a single page (topics, sections).
url_to_id = lambda u: parse_qs(urlparse(u).query).get('id', '')



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






def build_tree_for_language(parent_node, sourcetree):
    """
    Parse nodes given in `sourcetree` and add as children of `parent_node`.
    """
    EXPECTED_NODE_TYPES = ['TopicNode', 'AudioNode', 'DocumentNode', 'HTML5AppNode']

    for source_node in sourcetree:
        kind = source_node['kind']
        if kind not in EXPECTED_NODE_TYPES:
            logger.critical('Unexpected Node type found: ' + kind)
            raise NotImplementedError('Unexpected Node type found in channel json.')

        if kind == 'TopicNode':
            child_node = nodes.TopicNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            parent_node.add_child(child_node)
            source_tree_children = source_node.get("children", [])
            build_tree_for_language(child_node, source_tree_children)

        elif kind == 'AudioNode':
            child_node = nodes.AudioNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                # derive_thumbnail=True,                    # video-specific data
                thumbnail=source_node.get('thumbnail'),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        elif kind == 'DocumentNode':
            child_node = nodes.DocumentNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        elif kind == 'HTML5AppNode':
            child_node = nodes.HTML5AppNode(
                source_id=source_node["source_id"],
                title=source_node["title"],
                license=TESSA_LICENSE,
                author=source_node.get("author"),
                description=source_node.get("description"),
                thumbnail=source_node.get("thumbnail"),
            )
            add_files(child_node, source_node.get("files") or [])
            parent_node.add_child(child_node)

        else:
            logger.critical("Encountered an unknown content node format.")
            continue

    return parent_node

def add_files(node, file_list):
    EXPECTED_FILE_TYPES = ['VideoFile', 'ThumbnailFile', 'HTMLZipFile', 'DocumentFile']

    for f in file_list:

        file_type = f.get('file_type')
        if file_type not in EXPECTED_FILE_TYPES:
            logger.critical(file_type)
            raise NotImplementedError('Unexpected File type found in channel json.')

        path = f.get('path')  # usually a URL, not a local path

        # handle different types of files
        if file_type == 'VideoFile':
            node.add_file(files.VideoFile(path=f['path'], ffmpeg_settings=f.get('ffmpeg_settings')))
        elif file_type == 'ThumbnailFile':
            node.add_file(files.ThumbnailFile(path=path))
        elif file_type == 'HTMLZipFile':
            node.add_file(files.HTMLZipFile(path=path, language=f.get('language')))
        elif file_type == 'DocumentFile':
            node.add_file(files.DocumentFile(path=path, language=f.get('language')))
        else:
            raise UnknownFileTypeError("Unrecognized file type '{0}'".format(f['path']))




# from chef.crawl()
            # 2. save unfiltered data to chefdata/trees/
            file_name_tpl = CRAWLING_STAGE_OUTPUT_TPL.replace('.json', '_unfiltered.json')
            json_file_name = os.path.join(TREES_DATA_DIR, file_name_tpl.format(lang))
            with open(json_file_name, 'w') as json_file:
                json.dump(web_resource_tree, json_file, indent=2)
                print('Unfiltered result stored in ' + json_file_name)

            # 3. call filter_unwanted_categories and save filtered
            # filtered_wrt = filter_unwanted_categories(web_resource_tree)  # Disable so we scrape all
            filtered_wrt = web_resource_tree
            json_file_name = os.path.join(TREES_DATA_DIR, CRAWLING_STAGE_OUTPUT_TPL.format(lang))
            with open(json_file_name, 'w') as json_file:
                json.dump(filtered_wrt, json_file, indent=2)
                print('Filtered result stored in ' + json_file_name)




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
                print('Bold title:', title)
                title_el = title_b
                break

    if title_el is None:
        title_h4 = category.find('h4')
        if title_h4:
            title = get_text(title_h4)
            if len(title) > 0:
                print('H4 title:', title)
                title_el = title_h4

    if title_el is None:
        pre_description = ' '.join([get_text(p) for p in description_pars])
        description = pre_description.strip()
        print('Append description:', description[0:30]+'..')
        return 'append', None, description

    # extract title_el form DOM
    title_el.extract()

    pre_description = ' '.join([p.get_text().replace('\n',' ').strip() for p in description_pars])
    description = pre_description.strip()
    return 'new', title, description





def process_language_page(lang, page_url):
    """
    Process a top-level collection page for a given language.
    """
    page = get_parsed_html_from_url(page_url)

    web_resource_tree = dict(
        kind='TessaLangWebRessourceTree',
        title='TESSA (%s)' % lang.upper(),
        url=page_url,
        lang=lang,
        children=[],
    )

    pre_activity_links = page.find(class_="course-content").find_all("li", class_="activity")
    activity_links = list(pre_activity_links)
    print('\n\n')
    print('Processing TESSA page ', lang.upper(), '    num of unfiltered activity links:', len(activity_links))


    finished_with_modules = False
    current_category = None
    for activity in activity_links:
        # print(activity.text[0:50])
        activity_type = get_modtype(activity)

        # HEADINGS AND DESCRIPTIONS
        if activity_type in ['label', 'heading']:

            # Recognize when done with modules and starting "Additional resources" section
            activity_title = get_text(activity)
            if activity_title in ADDITIONAL_RESOURCES_TITLES:
                finished_with_modules = True

            # special handling for first list item--conatins ah-hoc formatted channel specific info
            if current_category is None and activity_type == 'label':
                channel_description = extract_channel_description(activity)
                web_resource_tree['description'] = channel_description
                current_category = {'title':'Something not-None that will be overwritten very soon...',
                                    'description':'',
                                    'children':[]}
                continue

            # skip last footer section
            home_link = activity.select('a[href="' + TESSA_HOME_URL + '"]')
            if home_link:
                print('Skipping footer section....')
                continue

            action, title, description = extract_category_from_modtype_label(activity)
            if action == 'new':
                new_category = dict(
                    kind='TessaCategory',
                    source_id='category_' + title.replace(' ', '_'),
                    title=title,
                    lang=lang,
                    description='',  # description, #        # Sept13hack
                    children = [],
                )
                web_resource_tree['children'].append(new_category)
                current_category = new_category
            elif action == 'append':
                current_category['description'] += ' ' + description   # TODO: add \n\n
            else:
                raise ValueError('Uknown action encountered:' + str(action) )

        # MODULE SUBPAGES
        elif activity_type == 'subpage' and finished_with_modules == False:
            info_dict = get_resource_info(activity)
            print('\n\nAdding subpage', info_dict['title'])
            subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=page_url)
            # print(info_dict)
            current_category['children'].append(subpage_node)


        # ADDITIONAL RESOURCES SUBPAGES
        elif activity_type == 'subpage' and finished_with_modules:
            info_dict = get_resource_info(activity)
            print('\n\nFound ADDITIONAL RESOURCES SUBPAGE', info_dict['title'])
            # TODO: remove one folder-deep, process title and description  :TODO:  :TODO:  :TODO:  :TODO:
            subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=page_url)
            # print(subpage_node)
            current_category['children'].append(subpage_node)


        # SPECIAL HANDLING FOR NON SUBPAGE CONTENT NODES
        elif activity_type == 'oucontent':
            outcontent_dict = get_resource_info(activity)
            print('Adding oucontent', outcontent_dict['title'])
            del outcontent_dict['type']
            outcontent_dict['kind'] = 'TessaContentPage'
            outcontent_dict['lang'] = lang
            current_category['children'].append(outcontent_dict)

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



def create_subpage_node(subpage_dict, lang=None, lang_main_menu_url=None):
    """
    Parse `TessaSubpage`-type objects linked to from the main language page.
    """
    url = subpage_dict["url"]
    print(url)
    topic_id = url_to_id(url)
    if not topic_id:
        print('ERROR: could not find topic_id in create_subpage_node')
        return
    topic_id = topic_id[0]


    subpage_node = dict(
        kind='TessaSubpage',
        url=url,
        source_id="topic_%s" % topic_id,
        title=subpage_dict["title"],
        lang=lang,
        description='', # TODO add descriptions for subpages....',
        children=[],
    )
    # print('    subpage_node: ' + str(subpage_node))

    # let's go get subpage contents...
    subpage = get_parsed_html_from_url(url)

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
                    print(' - Recognizd standard module structure. Taking whole module:')
                    print('   Content (%s):' % li_module_info['type'], li_module_info['title'])
                    del li_module_info['type']
                    li_module_info['kind'] = 'TessaModule'
                    li_module_info['lang'] = lang
                    subpage_node['children'].append(li_module_info)
                    # for li in rest:
                    #     print('    - skipping module section li', li.get_text())
                    all_items = section_li.find_all("li")
                    other_items = [item for item in all_items if item not in content_items]
                    for other_item in other_items:
                        print('    - skipping other li', get_text(other_item)[0:40])


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
        # print(' - Nonstandard module, using fallback strategies...')
        outer_section_li = section_lis[0]
        content_div = outer_section_li.find('div', class_="content", recusive=False)
        activity_lis = content_div.find('ul', class_='section').find_all('li', class_="activity")

        # Check if first item is subpage description (if more than 100 chars)
        first_activity = activity_lis[0]
        first_activity_text = get_text(first_activity)
        if len(first_activity_text) >= 100:
            subpage_node['description'] = first_activity_text
            activity_lis = activity_lis[1:]
        else:
            subpage_node['description'] = ''

        # process list of items using state machine
        # START = take content items until you find a label
        # SKIPNEXTLABEL = skip next label item (to skip: Read or download individual sec...)
        # SKIP = skip content items until next label (to skip individual sections files)
        state = 'START'
        current_subject = None
        sections_skipped = 0
        for activity_li in activity_lis:

            activity_type = get_modtype(activity_li)
            # print('Processing nonstandard activity_li (%s)' % activity_type, get_text(activity_li)[0:40])

            # skip back-to-menu links
            if activity_li.select('a[href="' + TESSA_HOME_URL + '"]'):
                # print('skipping TESSA_HOME_URL link activity')
                continue
            elif activity_li.select('a[href="' + lang_main_menu_url + '"]'):
                print('skipping lang_main_menu_url link-containing activity')   # this is not necessary since above will catch...
                continue

            # Main state-machine logic
            if state == 'START':
                if activity_type == 'label':
                    # beginning of a new subject
                    title = get_text(activity_li)
                    current_subject = dict(
                        kind='TessaSubject',
                        source_id=topic_id + ':' + title,
                        title=title,
                        children=[]
                    )
                    subpage_node['children'].append(current_subject)
                    state = 'SKIPNEXTLABEL'
                elif activity_type == 'oucontent':
                    print('should never be here >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
                    pass

            elif state == 'SKIPNEXTLABEL':
                if activity_type == 'label':
                    state = 'SKIP'
                elif activity_type == 'oucontent':
                    module_info = get_resource_info(activity_li)
                    print(' - NEW! Recognizd standard module structure. Taking whole module:')
                    print('   Content (%s):' % module_info['type'], module_info['title'])
                    del module_info['type']
                    module_info['kind'] = 'TessaModule'
                    module_info['lang'] = lang
                    current_subject['children'].append(module_info)
                elif activity_type == 'subpage':
                    info_dict = get_resource_info(activity_li)
                    print('ZZZZZZZ Adding subpage', info_dict['title'])
                    subpage_node = create_subpage_node(info_dict, lang=lang, lang_main_menu_url=lang_main_menu_url)
                    # print(info_dict)
                    current_subject['children'].append(subpage_node)

            elif state == 'SKIP':
                if activity_type == 'label':
                    # beginning of a new subject
                    title = get_text(activity_li)
                    current_subject = dict(
                        kind='TessaSubject',
                        source_id=topic_id + ':' + title,
                        title=title,
                        children=[]
                    )
                    subpage_node['children'].append(current_subject)
                    state = 'SKIPNEXTLABEL'
                    print('   total oucontent sections skipped in prev module =', sections_skipped)
                    sections_skipped = 0
                elif activity_type == 'oucontent':
                    # print('skipping section...')
                    sections_skipped += 1
                    continue

        # done processing NONSTANDARD MODULE
        print('   total oucontent sections skipped in prev module =', sections_skipped)

    else:
        print('Found third case')
        raise ValueError('found third case')


    return subpage_node










def filter_unwanted_categories(tree):
    filtered_resource_tree = tree.copy()
    filtered_resource_tree['children'] = []

    for category in tree['children']:

        filter_exclue_match_found = False
        for reject_title in REJECT_TITLES:
            #print('ZZZ'+reject_title+'ZZZ')
            if reject_title in category['title']:
                filter_exclue_match_found = True
                print('filter_exclue_match_found', reject_title)

        if filter_exclue_match_found:
            pass
        else:
            filtered_resource_tree['children'].append(category)

    return filtered_resource_tree


# def split_subpage_list_by_label(subpage, subpage_node, lang=None):
#     """
#     Fallback logic for Tessa subpages that do not consist of separate modules.
#     Implements an ad-hock strategy for grouping content items (`li.activity`)
#     into modules that contain content nodes.
#     """
#     pre_activity_links = subpage.find(class_="course-content").find_all("li", class_="activity")
#     activity_links = list(pre_activity_links)
#     print('         - ', 'Processing subpage', subpage_node['url'])
#     print('           ', 'Number of activity links:', len(activity_links))
#
#
#     def create_default_module(title, description, subpage_node):
#         """
#         If we encounter content item before a module has been created, we must
#         create a "default" using the info from the subpage.
#         """
#         default_module = dict(
#             kind='TessaModule',
#             title='FORCED::' + str(title) + 'maybe use ' + subpage_node['title'],
#             lang=lang,
#             description=description,
#             children = [],
#         )
#         return default_module
#
#     current_module = None
#     for activity in activity_links:
#         # print(activity.text[0:50])
#         activity_type = get_modtype(activity)
#
#         # HEADINGS AND DESCRIPTIONS
#         if activity_type in ['label', 'heading']:
#
#             # skip last footer section
#             home_link = activity.select('a[href="' + TESSA_HOME_URL + '"]')
#             if home_link:
#                 continue
#
#             action, title, description = extract_category_from_modtype_label(activity)
#             if action == 'new':
#                 new_module = dict(
#                     kind='TessaModule',
#                     title=title,
#                     lang=lang,
#                     description=description,
#                     children = [],
#                 )
#                 subpage_node['children'].append(new_module)
#                 current_module = new_module
#             elif action == 'append':
#                 if current_module:
#                     current_module['description'] += ' ' + description   # TODO: add \n\n
#                 else:
#                     new_module = create_default_module(title, description, subpage_node)
#                     subpage_node['children'].append(new_module)
#                     current_module = new_module
#             else:
#                 raise ValueError('Uknown action encountered:' + str(action) )
#
#         # SPECIAL HANDLING FOR NON SUBPAGE CONTENT NODES
#         elif activity_type == 'oucontent':
#             info_dict = get_resource_info(activity)
#             if current_module:
#                 current_module['children'].append(info_dict)
#             else:
#                 new_module = create_default_module('NO TITLE KNOWN', 'NO DESCRIPTION KNOWN', subpage_node)
#                 subpage_node['children'].append(new_module)
#                 current_module = new_module
#                 current_module['children'].append(info_dict)
#
#         # SUBPAGES WITHIN SUBPAGES
#         elif activity_type == 'subpage':
#             print('           ', 'Encountered subpage within subpage #### RECUSING VIA create_subpage_node ##########')
#             subsubpage_dict = get_resource_info(activity)
#             subsubpage_node = create_subpage_node(subsubpage_dict, lang=lang)
#             current_module['children'].append(subsubpage_node)
#
#         # ALSO TAKE PDF RESOURCES
#         elif activity_type == 'resource':
#             info_dict = get_resource_info(activity)
#             if 'pdf' in info_dict['title']:
#                 current_module['children'].append(info_dict)
#             else:
#                 print('           ', 'Ignoring activity of type', activity_type, '\tstartswith:',
#                       activity.get_text()[0:50].replace('\n',' '))
#
#
#         # REJECT EVERYTHING ELSE
#         else:
#             print('           ', 'Ignoring activity of type', activity_type, '\tstartswith:',
#                   activity.get_text()[0:50].replace('\n',' '))




# def old_build_tree_for_language(channel, language, lang_json_tree):
#     if language not in self.language_url_map:
#         print("Language not found")
#         return
#
#     top_level_url = self.language_url_map[language]
#     top_level_page = sess.get(top_level_url)
#     b = BeautifulSoup(top_level_page.content, "html5lib")
#     page_id = get_page_id(b)
#     subpages = {k:v for k,v in process_language_page(b).items() if any(x and x.get('type','') == 'Subpage' for x in v)}
#
#     for topic, subpages in subpages.items():
#         # Subject Resources
#         LOGGER.info('topic:' + str(topic))
#         topic_node = TopicNode(source_id=get_key(topic), title=topic)
#         channel.add_child(topic_node)
#         for subpage in subpages:
#             create_subpage_node(topic_node, subpage)
#
#     return channel



# def create_content_node(content_dict):
#     """
#     Returns a `TessaLangWebRessourceTree` dictionary with the informaiton necessary
#     for the scraping step.
#     """
#     source_id = url_to_id(content_dict['url'])
#     if not source_id:
#         return
#     source_id = source_id[0]
#     print('source_id', source_id)
#
#     content_node = dict(
#         kind='TessaLangWebRessourceTree',
#         url=content_dict['url'],
#         source_id=source_id,
#         title=content_dict['title'],
#         description=content_dict.get('description'),
#         # files=[HTMLZipFile(path=url)],
#         license=licenses.CC_BY_SA
#     )
#     return content_node



