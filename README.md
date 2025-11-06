# Bluetooth scanner for Search and Rescue (SAR) activities

SAR_BT_Scan is a software that was born from a need of SAR activities by our group. We can often assume that a missing person has some BT devices on or with them that are beaconing. This is something that we can ustilize in search activities. The scanner is constantly listening to Bluetooth beacons, geotagging and timestamping them and saving in a Sqlite database. Scanner is supposed to be traveling with rescuers and upon return to the commmand point, the data can be analyzed and visualized.

![Fragment of example resulting map processed with LLM tool](https://drive.google.com/uc?export=view&id=1T93QwNfIaOQkOVWXHegm51w6KZ1dYIt0)


The hardware setup is flexible, but the prototype is built on the following components and was not tested with any others:
- Raspberry PI 5 (4GB) / Raspberry PI OS
- TP-Link UB500 Plus (Bluetooth adapter with antenna)
- VK-162 GPS Receiver
- USB pendrive for data extraction
- Powerbank (with ~3W data draw measured, it should run over 10h with a decent 10.000 MAh powerbank)

![Prototype](https://drive.google.com/uc?export=view&id=1jDb16UQ4cg9WnSK-n0fTD6O_-fwnG6FV)

![Prototype](https://drive.google.com/uc?export=view&id=1cIs_jqTanOg82i_qh1hnH-aQ7wgvCcVy)

