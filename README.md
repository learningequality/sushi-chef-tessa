TESSA Sushi Chef
================


Install
-------

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements.txt


Running
-------

Need to run four separate chefs, one for each language

    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=en
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=fr
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=ar
    ./tessa_chef.py -v --token=<YOURTOKEN> --reset lang=sw

