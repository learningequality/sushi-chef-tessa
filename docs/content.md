
English:
http://www.open.edu/openlearncreate/course/view.php?id=2042


French:
https://translate.google.ca/translate?sl=auto&tl=en&js=y&prev=_t&hl=en&ie=UTF-8&u=http%3A%2F%2Fwww.open.edu%2Fopenlearncreate%2Fcourse%2Fview.php%3Fid%3D2046&edit-text=&act=url


Arabic:
https://translate.google.ca/translate?sl=auto&tl=en&js=y&prev=_t&hl=en&ie=UTF-8&u=http%3A%2F%2Fwww.open.edu%2Fopenlearncreate%2Fcourse%2Fview.php%3Fid%3D2198&edit-text=&act=url

Swahili:
https://translate.google.ca/translate?sl=auto&tl=en&js=y&prev=_t&hl=en&ie=UTF-8&u=http%3A%2F%2Fwww.open.edu%2Fopenlearncreate%2Fcourse%2Fview.php%3Fid%3D2199&edit-text=&act=url



Special cases:

  - some pages link to img resources, e.g.
    http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=80312&section=3
    which links to
    http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=80312&extra=thumbnail_idp36600944

  - Sometimes there is a subpage within a subpage
    http://www.open.edu/openlearncreate/mod/subpage/view.php?id=66699

  - Key resource links:
    Every language has a module/subpage with articles called "Key resources".
    These are sometimes linked-to within the learning modules, but these links
    won't work within the `iframe`s because they are ouside of the module.
    e.g.: module_1__personal_development___how_self_esteem_impacts_on_learning.html/Items/5x_tessa_eng_1_5.html
    contains the link (see [Key Resource: Using mind maps and brainstorming to explore ideas](http://www.open.edu/openlearnworks/mod/oucontent/olinkremote.php?website=TESSA_Eng&targetdoc=Key%20Resource:%20Using%20mind%20maps%20and%20brainstorming%20to%20explore%20ideas) )
      - What should we do with them?
      - Remove link and replace with full content tree full path within TESSA channel?

  - Should we keep the acknowledgements sections like this one:
    http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=81108&section=1.8
    Maybe just de-linkify the links?





Current scraper bugs / edge cases


          "lang": "en",
          "title": "Inclusive education toolkit Subpage",
          "url": "http://www.open.edu/openlearncreate/mod/subpage/view.php?id=80110",
          "kind": "TessaSubpage",
          "source_id": "subpage:80110",
          "children": [
            {
              "lang": "en",
              "title": "TESSA Inclusive Education Toolkit A guide to the education and training of teachers in inclusive education Website content",
              "url": "http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=81337",
              "kind": "TessaModule",
              "source_id": "oucontent:81337",
              "children": []
            },

            ^ first pages broken link "section-1.html" does not exist inside "12f985b0d4a76800b7d6b6e99ae19dab.zip"


            {
              "lang": "en",
              "title": "TESSA Inclusive Education Toolkit Website content",
              "url": "http://www.open.edu/openlearncreate/mod/oucontent/view.php?id=81618",
              "kind": "TessaModule",
              "source_id": "oucontent:81618",
              "children": []
            },


            ^ doesnt' render says needs js to render clickable concep map

