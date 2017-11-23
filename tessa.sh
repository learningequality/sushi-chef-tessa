#!/usr/bin/env bash

echo ""
echo "1. RUNNING TESSA Swahili >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
./tessa_chef.py  -v --reset --token=$STUDIO_TOKEN  lang=sw

echo ""
echo "2. RUNNING TESSA Arabic >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
./tessa_chef.py  -v --reset --token=$STUDIO_TOKEN  lang=ar

echo ""
echo "3. RUNNING TESSA Francais >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
./tessa_chef.py  -v --reset --token=$STUDIO_TOKEN  lang=fr

echo ""
echo "4. RUNNING TESSA English >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
./tessa_chef.py  -v --reset --token=$STUDIO_TOKEN  lang=en
