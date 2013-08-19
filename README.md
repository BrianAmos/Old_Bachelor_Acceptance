Short Description
-----------------

These scripts take a legislative district map defined by subunits of geography (state map using Census tracts in the provided example) and optimize it using the Old Bachelor Acceptance algorithm. Briefly, a random district is picked, a random neighboring tract is then flipped into the district, and the improvement to the overall map on compactness, county wholeness, population deviance, and racial majority-minority districts is measured. The changes that are improvements, or are within a threshold of decline in quality, are kept, and those that are not are rejected. The OBA algorithm is noteworthy in its non-monotonically changing threshold for acceptance - improvements decrease the threshold, declines increase the threshold. The map that had minimized the scoring function after a set number of attempts is chosen as the final map.


oldbacheloracceptance.py
------------------------

The main show. Requires a few things:

The MySQL for Python package. I used 1.2.2, since I'm running Python 2.6:
http://sourceforge.net/projects/mysql-python/

The statlib package:
https://code.google.com/p/python-statlib/

An input map where each line represents a Census tract (or whatever unit of geography you're using), with the format "Identifier,DistrictNumber". Tracts must be contiguous - meeting at a single point doesn't count - and must not have any holes inside them. Each tract must also be contiguous with at least one other tract. Sorry for the hassle.

A text file with the input map's district boundaries. Generating this is time-consuming, so I've chosen to do it beforehand - build_district_boundaries.py will generate this for you.

Three MySQL tables:

* one with a row for each tract, with data on each (e.g., population, area, etc.)
* one with neighbor relationships, with each row representing one pairing. Each pair should be entered twice, with the orders reversed
* one with the vertices for each tract

Example versions the five files are available, as well, and everything's set up in the script to run from them.

As the filename suggests, the algorithm used is Old Bachelor Acceptance, first described in:

Hu, T. C., Andrew B. Kahng and Chung-Wen Albert Tsao. 1995. "Old Bachelor Acceptance: A New Class of Non-Monotone Threshold Accepting Methods." ORSA Journal on Computing 7 (4): p. 417-426.

This particular implementation has an objective function that weights for two types of compactness, population deviance, the wholeness of counties within districts, and racial majority-minority districts. It has hard-coded the rejection of changes that would result in non-contiguity, and changes that would shift a district's population above or below a defined threshold.

Hopefully I've commented enough in the code to give you an idea of how it works.



build_district_boundaries.py
----------------------------

Generates the district boundary file needed for oldbacheloracceptance.py from the MySQL points table. Again, this is something that's slow enough that you want only want to do it once, instead of every time you run the script. Requires the MySQL module.



updatedb.py
-----------

Takes the output file of oldbacheloracceptance.py, and puts the district values into an existing shapefile for viewing in a program like ArcGIS. The ID field in your district assignment file should exist in the shapefile, and there should be a perfect match of tracts between them (no error checking, sorry).

Requires dbfpy: http://dbfpy.sourceforge.net/



examplefiles.zip
----------------

As the name implies, these are example files to test-run the script. Everything should be in place in the code to run them once you set up your MySQL tables.

* tractpoints.sql
* tractneighbor.sql
* tractdata.sql
* tractinitial40.txt
* boundary40.txt
* florida_example.zip

These should all be pretty self-explanatory. The three .sql's and two .txt's are needed to run oldbacheloracceptance.py, and florida_example.zip contains the shapefile that corresponds with everything. 

One note: since my script requires contiguous tracts without holes, I've had to merge some tracts together - the column "mergedwith" in tractdata lists the GeoIDs that have been merged into the parent tract (the populations, areas, etc. have been added together, so there's no loss there).


other info
-------------
* Brian Amos (brianamos@gmail.com)
* University of Florida
* http://www.brianamos.com/
* Last update: June 23, 2013
* Released under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 license.
* http://creativecommons.org/licenses/by-nc-sa/3.0/

