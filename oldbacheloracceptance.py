import _mysql
from math import ceil, sqrt
from statlib import stats
import random
import time



# predefined values
startingmap = "tractinitial40.txt" # the filename for the starting map. each line should be "geoid,district"
outputmap = "tractcurbest.txt" # the filename for the end map. same format as above
districtboundaryfile = "boundaryinitial40.txt" # district boundaries of input map. see build_district_boundaries.py
mysqlhostname = ""  # |
mysqlusername = ""  # |  set these for your particular MySQL set up.
mysqlpassword = ""  # |
mysqldatabase = ""  # |
mysqltractinfo = "tractdata"      # table with tract information
mysqlneighbors = "tractneighbor"  # table with neighbor relations
mysqlvertices = "tractpoints"     # table with tract vertices

population = 18801310 # state population
districts = 40 # number of districts you have
targetiter = 100000 # number of iterations you want the algorithm to run

countyweight = 4000   # county wholeness weight
popdevweight = 0.0004 # population deviance weight
compactweight = 200   # area/perimeter compactness weight
distweight = 1        # distance-from-centroid compactness weight
giniweight = 1000     # race proportions weight

'''
I don't do normalization of the portions of the objective function, so the weights have to do them. There's
a commented-out section of code below that you can run to get a feel for what each portion is contributing,
and adjust the weights accordingly.
'''

threshold = 3 # starting threshold. not especially important, since it'll eventually stabilize on its own
aadjustweight = .4 # weight for the threshold adjustment function in the case a change is accepted
radjustweight = .1 # weight for the threshold adjustment function in the case a change is rejected

'''
From tinkering around, it appears that the ratio of aadjustweight:radjustweight will roughly equal
the ratio of rejections to acceptances in the objective function, and as such, the average threshold
level. So, having that ratio be large will result in a lower average threshold, and a "pickier"
objective function. The magnitude of each weight changes the standard deviation of the threshold, so
larger values will give you wilder swings.
'''


targetpop = population/districts # ideal population for each district
minpop = targetpop - (targetpop * 0.03) # | if you want to set hard caps on how much a district's population can
maxpop = targetpop + (targetpop * 0.03) # | vary from the ideal, you can set that here.



def orientation(p,q,r):

    # used to calculate convex hull, code borrowed from David Eppstein: http://www.ics.uci.edu/~eppstein/ (public domain)
    
    '''Return positive if p-q-r are clockwise, neg if ccw, zero if colinear.'''
    return (float(q[1])-float(p[1]))*(float(r[0])-float(p[0])) - (float(q[0])-float(p[0]))*(float(r[1])-float(p[1]))


def getcenter(dist):

    # get the center of a convex hull created by the centroids of the tracts in a district

    templist = []
    finallist = []

    # get all the centroids of the members of the district

    for bginfo in attributes:

        if attributes[bginfo][13] == dist:

            templist.append(attributes[bginfo][1])

               
    # build a convex hull first, code borrowed from David Eppstein: http://www.ics.uci.edu/~eppstein/ (public domain)

    U = []
    L = []
    
    templist.sort()
    for p in templist:
        while len(U) > 1 and orientation(U[-2],U[-1],p) <= 0: U.pop()
        while len(L) > 1 and orientation(L[-2],L[-1],p) >= 0: L.pop()
        U.append(p)
        L.append(p)
    U.reverse()
    finallist = U[:-1] + L

    # end borrow

    # run a standard centroid formula

    xrunning = 0.0
    yrunning = 0.0
    arearunning = 0.0
    tempthing = 0.0

    for laststep in range(len(finallist) - 1):

        tempthing = ((finallist[laststep][0] * finallist[laststep + 1][1]) - (finallist[laststep + 1][0] * finallist[laststep][1]))
        xrunning += ((finallist[laststep][0] + finallist[laststep + 1][0]) * tempthing)
        yrunning += ((finallist[laststep][1] + finallist[laststep + 1][1]) * tempthing)
        arearunning += tempthing

    if arearunning == 0: print "Error in finding district centroid, convex hull has no area. District:", dist
        

    return (((1 / (3 * arearunning)) * xrunning), ((1 / (3 * arearunning)) * yrunning))

        

        

def getmeanstdev(dist, center):

    # find the mean and standard deviation of the distance of each tract in a district from its centroid

    buildlist = []
    for bginfo in attributes:

        if attributes[bginfo][13] == dist:

            buildlist.append(sqrt((center[0] - attributes[bginfo][1][0])**2 + (center[1] - attributes[bginfo][1][1])**2))

    return stats.mean(buildlist), stats.stdev(buildlist)


def getcurscore():

    # return objective score. this is only called at the beginning, since the score is updated with each change

    # perimeter vs. area compactness

    compactsum = 0.0

    for i in range(districts):

        compacttemp = (4 * 3.141593 * areas[i])/perimeters[i]**2
        compactsum += (1 - compacttemp)

    # distance-from-centroid compactness

    distsum = 0.0

    for bginfo in attributes:

        rawlength = sqrt((curcenters[attributes[bginfo][13]][0] - attributes[bginfo][1][0])**2 + (curcenters[attributes[bginfo][13]][1] - attributes[bginfo][1][1])**2)
        distsum += (rawlength - curmeans[attributes[bginfo][13]])/curstdevs[attributes[bginfo][13]]
        
    # county wholeness

    countysum = 0.0

    for coslice in countypop:

        cotemp = GRLC(countypop[coslice])
        countysum += (1 - cotemp[1])

    # race

    ginilist = getGINIList()
    tginisum = sum(ginilist)

    # population deviation

    popsum = 0

    i = 0
    while i < len(populations):

        popsum += abs(populations[i] - targetpop)
        i += 1

    return [countyweight * countysum, popdevweight * popsum, compactweight * compactsum, giniweight * tginisum, distweight * distsum]
        



def getGINIList():

    # seems redundant, and I could have set this up so that each race had its own portion of the objective score and removed the need for this
    # (the need being that you might want to emphasize one race's M-M districts stronger than another's). oh well.

    return [3 * (1 - getGINI(4,3)), 1 - getGINI(5,3)]



def spitValues(numer, denom):

    # returns the proportions of an attribute for each district. numer is the numerator value in the attributes dictionary (say, Hispanic VAP),
    # and denom is the denominator value (say, total VAP). if denom is given as -1, it gives a simple average of the numerator value.

    numsum = []
    densum = []
    finalvalues = []

    i = 0
    while i < districts:
        i += 1
        numsum.append(0)
        if denom == -1: densum.append(1)
        else: densum.append(0)

    for idnum in attributes:

        workdist = attributes[idnum][13]
        numsum[workdist] += attributes[idnum][numer]
        if not denom == -1: densum[workdist] += attributes[idnum][denom]

    i = 0
    while i < districts:
        if densum[i] == 0: finalvalues.append(0.0)
        else: finalvalues.append(float(numsum[i])/densum[i])
        i += 1

    return finalvalues


        

def getGINI(numer, denom):

    result = GRLC(spitValues(numer,denom))
    
    return result[1]


def GRLC(values):

    '''
    Created on July 24, 2011
    @author: Dilum Bandara
    @version: 0.1
    @license: Apache License v2.0

       Copyright 2012 H. M. N. Dilum Bandara, Colorado State University

       Licensed under the Apache License, Version 2.0 (the "License");
       you may not use this file except in compliance with the License.
       You may obtain a copy of the License at

           http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing, software
       distributed under the License is distributed on an "AS IS" BASIS,
       WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
       See the License for the specific language governing permissions and
       limitations under the License.
    '''

    # this function borrowed from Dilum Bandara, see above text. i removed portions that calculated the Robin Hood index,
    # and the original function returned the lorenz points, which i didn't need.

    '''
    Calculate Gini index, Gini coefficient, Robin Hood index, and points of 
    Lorenz curve based on the instructions given in 
    www.peterrosenmai.com/lorenz-curve-graphing-tool-and-gini-coefficient-calculator
    Lorenz curve values as given as lists of x & y points [[x1, x2], [y1, y2]]
    @param values: List of values
    @return: [Gini index, Gini coefficient, Robin Hood index, [Lorenz curve]] 
    '''
    
    n = len(values)
    assert(n > 0), 'Empty list of values'
    sortedValues = sorted(values) #Sort smallest to largest

    #Find cumulative totals
    cumm = [0]
    for i in range(n):
        cumm.append(sum(sortedValues[0:(i + 1)]))

    #Calculate Lorenz points
    LorenzPoints = [[], []]
    sumYs = 0           #Some of all y values
    for i in range(1, n + 2):
        x = 100.0 * (i - 1)/n
        y = 100.0 * (cumm[i - 1]/float(cumm[n]))
        sumYs += y
    
    giniIdx = 100 + (100 - 2 * sumYs)/n #Gini index 

    return [giniIdx, giniIdx/100]


def buildneighborbgs(dist):

    # takes a district number, returns all the neighboring tracts to the district

    templist = []
    comparelist = []

    for bginfo in attributes:

        if (attributes[bginfo][13] == dist):

            templist.extend(attributes[bginfo][14])
            comparelist.append(bginfo)

    return list(set(templist)-set(comparelist))


def buildmemberbgs(dist):

    # returns the tracts in district dist

    templist = []

    for bginfo in attributes:

        if attributes[bginfo][13] == dist:

            templist.append(bginfo)

    return templist

def reassignpiece(oldpiece, newpiece):

    # for use in checking for district contiguity

    for checkingpiece in range(len(piecelist)):

        if piecelist[checkingpiece] == oldpiece:

            piecelist[checkingpiece] = newpiece



#initialize lists
ginilist = []
countypop = {}
curcenters = []
curstdevs = []
curmeans = []
populations = []
areas = []
perimeters = []
districtboundaries = []

i = 0
while i < districts:
    i += 1
    populations.append(0)
    areas.append(0.0)
    perimeters.append(0.0)
    districtboundaries.append([])
    curcenters.append((0.0, 0.0))
    curstdevs.append(0.0)
    curmeans.append(0.0)


'''
This is where attributes are loaded up. Basically all the data on each tract (except vertices) are in a dictionary
object called "attributes". The keys are the geoids, and the values are a list of various tract attributes, with the
following indexes:

0: County FIPS Code
1: Tract Centroid (x,y)
2: Population (2010 Census)
3: Voting Age Population (i.e., 18 or over) (2010 Census)
4: Black VAP (2010 Census)
5: Hispanic VAP (2010 Census)
6: Senior Citizens (from the American Community Survey)
7: Number of Workers (ACS)
8: Workers in Agriculture (ACS)
9: Workers in Manufacturing (ACS)
10: Workers in Retail (ACS)
11: Population (as given by the ACS, which is an estimation using data over five years, so it'll be different)
12: Population in College (ACS)
13: District Number
14: List of Neighboring Tracts
15: (empty - used to be something else)
16: Placeholder for Checking for Contiguity
17: Tract Area

Sorry for hard-coding the numbers and making it a pain in the ass for you to change them.
'''
    
db=_mysql.connect(mysqlhostname,mysqlusername,mysqlpassword,mysqldatabase)
db.query("SELECT * FROM " + mysqltractinfo + " WHERE 1 ORDER BY geoid")
r=db.use_result()
secdb=_mysql.connect(mysqlhostname,mysqlusername,mysqlpassword,mysqldatabase)
secdb.query("SELECT * FROM " + mysqlneighbors + " WHERE 1 ORDER BY `from`")
secr=secdb.use_result()
vertdb=_mysql.connect(mysqlhostname,mysqlusername,mysqlpassword,mysqldatabase)
vertdb.query("SELECT * FROM " + mysqlvertices + " WHERE 1 ORDER BY geoid,geopid")
vertr=vertdb.use_result()

curvert = vertr.fetch_row()
neighbors = secr.fetch_row()
attributes = {}
vertices = {}
tempdists = {}


f = open(startingmap, "r")
for line in f:
    line = line.rstrip()
    pieces = line.split(",")
    tempdists[pieces[0]] = pieces[1]

f.close()

point = r.fetch_row()

while point:

    
    attributes[point[0][1]] = [int(point[0][2]), (float(point[0][4]), float(point[0][5])), int(point[0][6]), int(point[0][7]), int(point[0][8]), int(point[0][9]), int(point[0][10]), int(point[0][11]), int(point[0][12]), int(point[0][13]), int(point[0][14]), int(point[0][15]), int(point[0][18]), int(tempdists[point[0][1]])] 

    templist = []

    while neighbors:

        if neighbors[0][1] == point[0][1]:
            templist.append(neighbors[0][2])
            neighbors = secr.fetch_row()
        else:
            break

    tempvertlist = []

    while curvert:

        if curvert[0][1] == point[0][1]:
            tempvertlist.append((float(curvert[0][3]),float(curvert[0][4])))
            curvert = vertr.fetch_row()
        else:
            break

    vertices[point[0][1]] = tempvertlist

    attributes[point[0][1]].append(templist)

    attributes[point[0][1]].append(0) # not in use

    attributes[point[0][1]].append(-1)

    attributes[point[0][1]].append(float(point[0][21]))

    
    point = r.fetch_row()

del db
del secdb
del tempdists





print "attributes loaded"

# initialize some variables that will be used throughout the process

checkcounties = []

for bginfo in attributes:
    if (checkcounties.count(attributes[bginfo][0]) == 0):
        checkcounties.append(attributes[bginfo][0])


for i in checkcounties:
    countypop[i] = []
    countypop[i].extend(populations)

for bginfo in attributes:

    areas[attributes[bginfo][13]] += attributes[bginfo][17]
    countypop[attributes[bginfo][0]][attributes[bginfo][13]] = countypop[attributes[bginfo][0]][attributes[bginfo][13]] + attributes[bginfo][2]
    populations[attributes[bginfo][13]] = populations[attributes[bginfo][13]] + attributes[bginfo][2]


for dist in range(districts):
    curcenters[dist] = getcenter(dist)

for dist in range(districts):
    curmeans[dist], curstdevs[dist] = getmeanstdev(dist, curcenters[dist])


# load up the district boundaries

f = open(districtboundaryfile, "r")
curdist = -1

for nextline in f:

    nextline = nextline.rstrip()
    pieces = nextline.split(",")

    if len(pieces) == 1:

        curdist = int(pieces[0])
        continue

    districtboundaries[curdist].append((float(pieces[0]),float(pieces[1])))

f.close()


for i in range(districts):

    newvalue = districtboundaries[i][len(districtboundaries[i]) - 1]
    curpertotal = 0.0

    for j in range(len(districtboundaries[i])):

        oldvalue = newvalue
        newvalue = districtboundaries[i][j]

        curpertotal += sqrt((oldvalue[0] - newvalue[0])**2 + (oldvalue[1] - newvalue[1])**2)

    perimeters[i] = curpertotal


ginilist = getGINIList()
ginisum = sum(ginilist)

neighbordict = {}

i = 0
for i in range(districts):

    neighbordict[i] = buildneighborbgs(i)


curobjectivescore = sum(getcurscore())
curminoscore = curobjectivescore

curiter = 0
switches = 0
rejections = 0

# i used these to help figure out the behavior of the threshold adjustment weights
totswitches = 0
totrejections = 0
sumthresh = 0.0





# alright, everything's ready to go. main loop starts here.

while curiter < targetiter:

    curiter = curiter + 1

    if curiter % 500 == 0:

        # finding district centers, means, and standard deviations is relatively time-consuming, and the values don't change
        # all that much on small time scales, so I don't do them with every tract reassignment

        for dist in range(districts):
            curcenters[dist] = getcenter(dist)

        for dist in range(districts):
            curmeans[dist], curstdevs[dist] = getmeanstdev(dist, curcenters[dist])

        # spit out information every so often on how things are going

        print "------------"
        print "Iteration Count:", curiter, "To Go:", targetiter - curiter
        print "Current Threshold:", threshold
        print "Current Objective Score:", curobjectivescore, "Best:", curminoscore
        print "Switches:", switches, "Rejections:", rejections
        print "------------"
        totswitches += switches
        totrejections += rejections
        switches = 0
        rejections = 0

    curdist = random.randint(0, districts - 1)  # pick a random district to work with

    if populations[curdist] > maxpop: continue  # bail out now if the population is above the hard-coded level

    potential = neighbordict[curdist]  # get the district's neighbors

    if potential == 0:  # if there aren't any neighbors, something's gone terribly wrong.

        print "Error: District", curdist, "has no neighbors"
        continue

    # pick a random neighbor. the rest of the process will be testing if flipping it into the current district
    # helps or hurts the map
    
    getid = random.randint(0, len(potential) - 1)  
    check = potential[getid]

    otherdist = attributes[check][13]

    if populations[otherdist] < minpop: continue  # bail out now if the district we're taking from has too small a population
    
    attributes[check][13] = curdist
    dist = otherdist

    '''
    what follows is the contiguity check. it's not especially intuitive, but it's considerably faster than other methods i tried.
    the end result will be that each tract will be assigned a number corresponding to an index in piecelist, and each member
    of piecelist will also refer to an index in piecelist. the number of unique values will be the number of non-contiguous
    piecs in the district we're taking from - if it's anything but 1, we reject it. i don't do it here, but if you wrote an
    algorithm that did allow for non-contiguity to arise, you could add on a bit to reassign pieces using the numbers given
    to each tract.
    '''

    workingdist = buildmemberbgs(dist)

    for assignpiece in workingdist:

        attributes[assignpiece][16] = -1

    piececount = -1
    workingpieceno = 0

    piecelist = []
    piecepops = []

    for assignpiece in workingdist:

        if attributes[assignpiece][16] == -1:

            piececount += 1
            workingpieceno = piececount
            piecelist.append(workingpieceno)
            attributes[assignpiece][16] = workingpieceno

        else:

            workingpieceno = piecelist[attributes[assignpiece][16]]


        for setneigh in attributes[assignpiece][14]:

            if attributes[setneigh][13] == attributes[assignpiece][13]:

                if not (attributes[setneigh][16] == -1 or piecelist[attributes[setneigh][16]] == workingpieceno):

                    reassignpiece(piecelist[attributes[setneigh][16]], workingpieceno)

                else:

                    attributes[setneigh][16] = workingpieceno

    # the change would create a non-contiguity. flip the tract back and end now.

    if len(set(piecelist)) > 1:

        attributes[check][13] = otherdist
        continue

    # distance-from-centroid compactness

    areaconvex = sqrt((curcenters[curdist][0] - attributes[check][1][0])**2 + (curcenters[curdist][1] - attributes[check][1][1])**2)
    areadiff1 = (areaconvex - curmeans[curdist])/curstdevs[curdist]

    areaconvex = sqrt((curcenters[otherdist][0] - attributes[check][1][0])**2 + (curcenters[otherdist][1] - attributes[check][1][1])**2)
    areadiff2 = (areaconvex - curmeans[otherdist])/curstdevs[otherdist]

    # i use gini coefficients to test the wholeness of counties

    propslice = []
    propslice.extend(countypop[attributes[check][0]])

    startcotemp = GRLC(propslice)
    startcogini = 1 - startcotemp[1]

    propslice[curdist] += attributes[check][2]
    propslice[otherdist] -= attributes[check][2]

    endcotemp = GRLC(propslice)
    endcogini = 1 - endcotemp[1]

    # population deviance

    popdev11 = abs(populations[curdist] - targetpop + attributes[check][2])
    popdev12 = abs(populations[curdist] - targetpop)
    popdev21 = abs(populations[otherdist] - targetpop - attributes[check][2])
    popdev22 = abs(populations[otherdist] - targetpop)

    popdev1 = popdev11 - popdev12
    popdev2 = popdev21 - popdev22


    # perimeter vs. area compactness.
    
    #build new perimeter. first, get the vertices of the two affected districts
   
    curvertlist = []
    othervertlist = []
    checkvertlist = []

    for buildcheck in attributes[check][14]:

        if attributes[buildcheck][13] == curdist:

            for i in range(len(vertices[buildcheck]) - 1):

                curvertlist.append((vertices[buildcheck][i+1][0],vertices[buildcheck][i+1][1],vertices[buildcheck][i][0],vertices[buildcheck][i][1]))

            curvertlist.append((vertices[buildcheck][0][0],vertices[buildcheck][0][1],vertices[buildcheck][len(vertices[buildcheck]) - 1][0],vertices[buildcheck][len(vertices[buildcheck])-1][1]))

        if attributes[buildcheck][13] == otherdist:

            for i in range(len(vertices[buildcheck]) - 1):

                othervertlist.append((vertices[buildcheck][i+1][0],vertices[buildcheck][i+1][1],vertices[buildcheck][i][0],vertices[buildcheck][i][1]))

            othervertlist.append((vertices[buildcheck][0][0],vertices[buildcheck][0][1],vertices[buildcheck][len(vertices[buildcheck]) - 1][0],vertices[buildcheck][len(vertices[buildcheck])-1][1]))

    for i in range(len(vertices[check]) - 1):

        checkvertlist.append((vertices[check][i][0],vertices[check][i][1],vertices[check][i+1][0],vertices[check][i+1][1]))

    checkvertlist.append((vertices[check][len(vertices[check])-1][0],vertices[check][len(vertices[check])-1][1],vertices[check][0][0],vertices[check][0][1]))



    #find the "starting point" where the tract will contribute uniquely to the district border.
    #start with the first point in the vertex list of the tract. if it's not unique, go forward til we find that point

    if curvertlist.count(checkvertlist[0]) > 0:

        i = 0
        while curvertlist.count(checkvertlist[i]) > 0: i += 1

        startunique = i

    #we've hit a unique point at the start. work backwards until it isn't.

    else:

        i = len(checkvertlist) - 1
        while curvertlist.count(checkvertlist[i]) == 0: i -= 1

        startunique = i+1
        if startunique == len(checkvertlist): startunique = 0

    #now find the end point, calculating the length along the way.

    addedperimeter = 0.0
    endunique = startunique

    while curvertlist.count(checkvertlist[endunique]) == 0:

        addedperimeter += sqrt((checkvertlist[endunique][0] - checkvertlist[endunique][2])**2 + (checkvertlist[endunique][1] - checkvertlist[endunique][3])**2)
        endunique += 1
        if endunique == len(vertices[check]): endunique = 0

    
    #now work our way around to the start again, to get that portion of the perimeter

    removedperimeter = 0.0
    tempcount = endunique + 1
    tempprevious = endunique
    if tempcount == len(vertices[check]): tempcount = 0

    while tempprevious != startunique:

        removedperimeter += sqrt((vertices[check][tempcount][0] - vertices[check][tempprevious][0])**2 + (vertices[check][tempcount][1] - vertices[check][tempprevious][1])**2)
        tempprevious = tempcount
        tempcount += 1
        if tempcount == len(vertices[check]): tempcount = 0

    #alright, ready to calculate the change

    oldcurcompact = 1 - ((4 * 3.141593 * areas[curdist])/perimeters[curdist]**2)
    newcurcompact = 1 - ((4 * 3.141593 * (areas[curdist] + attributes[check][17]))/(perimeters[curdist] + addedperimeter - removedperimeter)**2)

    compact1 = newcurcompact - oldcurcompact

    if (startunique < endunique): newvertslice = vertices[check][startunique:endunique+1]
    else: newvertslice = vertices[check][startunique:] + vertices[check][:endunique+1]

    curperchange = addedperimeter - removedperimeter

    #do the whole thing again, but with the source district. the unique part is what's being removed, though.

    if othervertlist.count(checkvertlist[0]) > 0:

        i = 0
        while othervertlist.count(checkvertlist[i]) > 0: i += 1

        startunique = i

    #we've hit a unique point at the start. work backwards until it isn't.

    else:

        i = len(checkvertlist) - 1
        while othervertlist.count(checkvertlist[i]) == 0: i -= 1

        startunique = i+1
        if startunique == len(vertices[check]): startunique = 0

    #now find the end point, calculating the length along the way.

    removedperimeter = 0.0
    endunique = startunique

    while othervertlist.count(checkvertlist[endunique]) == 0:

        removedperimeter += sqrt((checkvertlist[endunique][0] - checkvertlist[endunique][2])**2 + (checkvertlist[endunique][1] - checkvertlist[endunique][3])**2)
        endunique += 1
        if endunique == len(vertices[check]): endunique = 0
    
    #now work our way around to the start again, to get that portion of the perimeter

    addedperimeter = 0.0
    tempcount = endunique + 1
    tempprevious = endunique
    if tempcount == len(vertices[check]): tempcount = 0

    while tempprevious != startunique:

        addedperimeter += sqrt((vertices[check][tempcount][0] - vertices[check][tempprevious][0])**2 + (vertices[check][tempcount][1] - vertices[check][tempprevious][1])**2)
        tempprevious = tempcount
        tempcount += 1
        if tempcount == len(vertices[check]): tempcount = 0   

    #alright, ready to calculate the change

    oldothercompact = 1 - ((4 * 3.141593 * areas[otherdist])/perimeters[otherdist]**2)
    newothercompact = 1 - ((4 * 3.141593 * (areas[otherdist] - attributes[check][17]))/(perimeters[otherdist] + addedperimeter - removedperimeter)**2)

    compact2 = newothercompact - oldothercompact

    if (endunique < startunique): oldvertslice = vertices[check][endunique:startunique+1]
    else: oldvertslice = vertices[check][endunique:] + vertices[check][:startunique+1]

    otherperchange = addedperimeter - removedperimeter

    # i also use gini coefficients for the racial majority-minority district creation
    
    ginilist = getGINIList()
    newginisum = sum(ginilist)


    # alright, here's the objective function. we're looking to minimize the score, so lower is better
    
    checkdiff = (distweight * (areadiff1 - areadiff2)) + (compactweight * (compact1 + compact2)) + (countyweight * (endcogini - startcogini)) + (popdevweight * (popdev1 + popdev2)) + (giniweight * (newginisum - ginisum))

    '''
    # if you want information about how each portion of the objective function is contributing, uncomment this
    print "compact: ", compactweight * (compact1 + compact2), compact1, compact2
    print "distance compactness: ", distweight * (areadiff1 - areadiff2)
    print "county: ", countyweight * (endcogini - startcogini)
    print "popdev: ", popdevweight * (popdev1 + popdev2)
    print "gini: ", giniweight * (newginisum - ginisum)
    print checkdiff, threshold
    '''

    # the cool part about the OBA algorithm is its threshold, which allows for changes that make the map worse in an attempt to ultimately improve it.
    # the adjustments make it non-monotonic, which is doubly cool. each rejection raises the threshold, each acceptance lowers it.
    
    if checkdiff - threshold > 0:

        # the change is too much of a detriment, so let's reject it.

        attributes[check][13] = otherdist
        threshold = threshold + (radjustweight * (1 - (float(curiter)/targetiter)))
        rejections += 1

        sumthresh += threshold
        
        
        continue

    else:

        # the change is an improvement, or within the threshold. let's update everything to keep the change.

        # neighbor relations are stored in neighbordict, so update that.

        neighbordict[curdist].remove(check)
        neighbordict[otherdist].append(check)

        for checkneigh in attributes[check][14]:

            if not attributes[checkneigh][13] == curdist:

                neighbordict[curdist].append(checkneigh)
                neighbordict[curdist] = list(set(neighbordict[curdist]))

            if not attributes[checkneigh][13] == otherdist:

                neighbordict[otherdist].remove(checkneigh)

                for finalcheck in attributes[checkneigh][14]:

                    if attributes[finalcheck][13] == otherdist:

                        neighbordict[otherdist].append(checkneigh)
                        neighbordict[otherdist] = list(set(neighbordict[otherdist]))


        ginisum = newginisum # racial ginis
        

        # populations of each district in each county

        countypop[attributes[check][0]][curdist] += attributes[check][2]
        countypop[attributes[check][0]][otherdist] -= attributes[check][2]

        # district populations

        populations[curdist] += attributes[check][2]
        populations[otherdist] -= attributes[check][2]

        # district areas

        areas[curdist] += attributes[check][17]
        areas[otherdist] -= attributes[check][17]

        # district perimeters

        perimeters[curdist] += curperchange
        perimeters[otherdist] += otherperchange

        # update the district boundary coordinates

        startextract = districtboundaries[curdist].index(newvertslice[0])
        endextract = districtboundaries[curdist].index(newvertslice[len(newvertslice) - 1])

        oldvertslice.reverse()

        if startextract < endextract:

            districtboundaries[curdist] = districtboundaries[curdist][:startextract] + newvertslice[:-1] + districtboundaries[curdist][endextract:]

        else:

            districtboundaries[curdist] = districtboundaries[curdist][endextract:startextract] + newvertslice[:-1]

        startextract = districtboundaries[otherdist].index(oldvertslice[0])
        endextract = districtboundaries[otherdist].index(oldvertslice[len(oldvertslice) - 1])

        if startextract < endextract:

            districtboundaries[otherdist] = districtboundaries[otherdist][:startextract] + oldvertslice[:-1] + districtboundaries[otherdist][endextract:]

        else:

            districtboundaries[otherdist] = districtboundaries[otherdist][endextract:startextract] + oldvertslice[:-1]
        

        threshold = threshold - (aadjustweight * (1 - (float(curiter)/targetiter))) # adjust the threshold

        sumthresh += threshold

        switches += 1

        curobjectivescore += checkdiff  # update the current objective score

        if curobjectivescore < curminoscore:

            # if the new objective score is the lowest we've encountered, we've got a new best map. output it to a text file.

            curminoscore = curobjectivescore

            print "new record: ", curminoscore

            f = open(outputmap, 'w')

            for bginfo in attributes:

                f.write("{0},{1}\n".format(bginfo, attributes[bginfo][13]))

            f.close()

'''
            # this is a bit of error checking that creates a file that can be loaded into arcgis using the Samples toolbox.
            # when i was writing this, i wanted to make sure the district boundaries in memory matched what the district
            # assignments showed. it's relatively slow, though, so i don't leave it running.
            
            f = open('errorcheckbound.txt', 'w')

            f.write("Polygon\n")

            for i in range(districts):

                newdistline = str(i) + " 0\n"
                f.write(newdistline)

                counter = 0

                for onepoint in districtboundaries[i]:

                    putpoint = str(counter) + " " + str(onepoint[0] * 1000) + " " + str(onepoint[1] * 1000) + " nan nan\n"
                    f.write(putpoint)

            f.write("END")

            f.close()

'''
