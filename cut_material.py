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


