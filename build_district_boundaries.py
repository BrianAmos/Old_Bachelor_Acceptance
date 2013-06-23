import _mysql

# predefined values
maptofind = "tractinitial40.txt" # the filename of the map to create district boundaries for. each line should be "geoid,district"
districtboundaryfile = "boundaryinitial402.txt" # output file for use in oldbacheloracceptance.py
mysqlhostname = ""  # |
mysqlusername = ""  # |  set these for your particular MySQL set up.
mysqlpassword = ""  # |
mysqldatabase = ""  # |
mysqlvertices = "tractpoints"  # table with tract vertices

districts = 40
attributes = {}
districtboundaries = []
vertices = {}

for dist in range(districts):
    districtboundaries.append([])


#load attributes into memory
f = open(maptofind, "r")
for line in f:
    line = line.rstrip()
    pieces = line.split(",")
    attributes[pieces[0]] = int(pieces[1])

f.close()


vertdb=_mysql.connect(mysqlhostname,mysqlusername,mysqlpassword,mysqldatabase)
vertdb.query("SELECT * FROM " + mysqlvertices + " WHERE 1 ORDER BY geoid,geopid")
vertr=vertdb.use_result()

curvert = vertr.fetch_row()

currenttract = curvert[0][1]
tempvertlist = []

while curvert:

    if curvert[0][1] == currenttract:
        tempvertlist.append((float(curvert[0][3]),float(curvert[0][4])))
    else:
        vertices[currenttract] = tempvertlist
        currenttract = curvert[0][1]
        tempvertlist = []
        tempvertlist.append((float(curvert[0][3]),float(curvert[0][4])))

    curvert = vertr.fetch_row()

vertices[currenttract] = tempvertlist

del vertdb


print "start building dists"

for dist in range(districts):
    
    fullpointlist = []
    distmembership = []

    for bginfo in attributes:

        if attributes[bginfo] == dist:

            distmembership.append(bginfo)
            fullpointlist.extend(vertices[bginfo])

    #find the easternmost point in the district, and use it as a starting point. guaranteed to be on the border of the district

    startingvert = (-1000.0,-1000.0)  # arbitrary values lower than the lowest x or y values in the dataset

    for checkpoint in fullpointlist:

        if checkpoint[0] > startingvert[0]:

            startingvert = checkpoint

    #find out which tracts have that point

    ownerlist = []

    for bginfo in distmembership:

        if vertices[bginfo].count(startingvert) > 0:

            ownerlist.append(bginfo)

    #it's possible that it's not a unique point, it could happen at the meeting of two tracts

    if len(ownerlist) > 1:

        startingowner = ""

        for checkverts in ownerlist:

            tempindex = vertices[checkverts].index(startingvert) + 1
            if tempindex == len(vertices[checkverts]): tempindex = 0
            tempnextvert = vertices[checkverts][tempindex]

            if fullpointlist.count(tempnextvert) == 1:

                if startingowner != "":

                    print "oops big mistake: two unique next entries"

                startingowner = checkverts

        if startingowner == "":

            print "oops big mistake: no unique next entry"

    if len(ownerlist) == 0:

        print "oops big mistake: no match for an owner"

    if len(ownerlist) == 1:

        startingowner = ownerlist[0]

    districtboundaries[dist].append(startingvert)

    #let's start the major loop, then. endless loop, probably a bad idea. oh well.

    curowner = startingowner
    curvert = startingvert

    while 1:

        tempindex = vertices[curowner].index(curvert) + 1

        #loop back to the start of the list if necessary

        if tempindex == len(vertices[curowner]): tempindex = 0

        curvert = vertices[curowner][tempindex]

        if curvert == startingvert: break #back to the start

        districtboundaries[dist].append(curvert)

        if fullpointlist.count(curvert) == 1: continue

        else: #we've hit another tract. let's jump to it. 

            ownerlist = []

            for bginfo in distmembership:

                if vertices[bginfo].count(curvert) > 0 and bginfo != curowner:

                    ownerlist.append(bginfo)

            if len(ownerlist) > 1: #there's a chance it's a meeting of three tracts, deal with that

                curowner = ""

                for checkverts in ownerlist:

                    tempindex = vertices[checkverts].index(curvert) + 1
                    if tempindex == len(vertices[checkverts]): tempindex = 0
                    tempnextvert = vertices[checkverts][tempindex]


                    if fullpointlist.count(tempnextvert) == 1:


                        if curowner != "":

                            print "oops big mistake: two unique next entries in going to a new tract"

                        curowner = checkverts

                if curowner == "":

                    print "oops deadly mistake: no unique next entry in going to a new tract"
                    print ownerlist, curvert, curowner
                    sys.exit(1)

            if len(ownerlist) == 0:

                print "oops deadly mistake: no match for an owner in going to a new tract"
                print ownerlist, curvert, curowner
                sys.exit(1)

            if len(ownerlist) == 1:

                curowner = ownerlist[0]

    print dist, startingowner, startingvert

print "end building dists"

# write the results

f = open(districtboundaryfile, 'w')

i = 0
for i in range(districts):

    headertext = str(i) + "\n"
    f.write(headertext)

    for nextpoint in districtboundaries[i]:

        nextline = str(nextpoint[0]) + "," + str(nextpoint[1]) + '\n'
        f.write(nextline)
                        

    i += 1

f.close()
