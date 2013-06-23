from dbfpy import dbf

districtsfile = "tractinitial40.txt"  # the district values you want to use
mapdbf = "florida_example.dbf" # the .dbf file of the shapefile you want to update

dists = {}

f = open(districtsfile, "r")
for line in f:
    line = line.rstrip()
    pieces = line.split(",")
    dists[pieces[0]] = pieces[1]

f.close()

db = dbf.Dbf(mapdbf)

for rec in db:

    rec["DIST"] = float(dists[rec["GEOID10"]])
    rec.store()

