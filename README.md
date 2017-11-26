TESSA Sushi Chef
================

Related docs
------------
  - [spec doc](https://docs.google.com/document/d/1JD3M_ll7BUSaqHewhcCInj3leGAsRlFtJHc2qoTTUeM/edit#)
  - [trello card](https://trello.com/c/AWsJ86VU/28-tessa)



TODO
----

  - Handle titles using `get_resource_info` not `get_title` (to avoid Subpage in title)
  - 


Install
-------

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements.txt


Running
-------

Need to start four separate chefs runs, one for each language:

    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=sw
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=ar
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=fr
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=en


