
Design
======



Crawling step
-------------
Starting from the four "main" pages for each language (All of Africa), the first
step is to figure out what resources we will extract and save a json file with
the full web resource tree in the directory [chefdata/trees/](../chefdata/trees/).


For example, crawling the [TESSA - English - All Africa page](http://www.open.edu/openlearncreate/course/view.php?id=2042)
will produce the following files in the directory `chefdata/trees/`:
  - `chefdata/trees/web_resource_tree_en_unfiltered.json`, which contains the raw
    scrape of the content items
  - `chefdata/trees/web_resource_tree_en.json`, which has certain items filtered
    like the link to PDFs and DOCs and the TESSA share drive
