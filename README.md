DeSSE - Demon's Souls Server Emulator

This is a very quick and dirty server emulator that supports the most basic features.
Working at the moment:

 - matchmaking (only internally in each region, EU/US people won't see each other's summon signs for example)
 - messages, pre-seeded with some old EU messages, but new messages have priority
 - ghosts
 - bloodstains, only pre-seeded with old EU stains, new stains not supported yet
 
The matchmaking only works by virtue of Sony's matchmaking servers being online. I don't know
if these servers are generic and will continue working in the future or if they might
be turned off at some point. It works right now, at least.
 
Requirements:

 - python 2.6/2.7
 - pycrypto
 

Setup:

 - set up some kind of DNS proxy (I used https://github.com/Crypt0s/FakeDns - edit the remote.conf file and insert your server's IP)
 - edit info.ss and insert your server's IP
 - run server with `python emulator.py`
 
Everyone that wants to connect to the server needs to configure the DNS to point to your DNS proxy in their PS3 network settings.
No other changes should be necessary.