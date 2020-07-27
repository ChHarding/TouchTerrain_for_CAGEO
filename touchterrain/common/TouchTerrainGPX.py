import time 
import math


def plotLineHigh(x0,y0,x1,y1,height,npim,pathedPoints,averagePathHeight,thicknessOffset): 
    dx = x1 - x0
    dy = y1 - y0
    xi = 1

    if dx < 0:
        xi = -1
        dx = -dx
    
    D = 2*dx - dy
    x = x0

    for y in range(y0,y1+1):
        plotPoint(x,y,height,npim,pathedPoints,averagePathHeight,thicknessOffset)
        if D > 0:
            x = x + xi
            D = D - 2*dy

        D = D + 2*dx





def plotLineLow(x0,y0,x1,y1,height,npim,pathedPoints,averagePathHeight,thicknessOffset):
   
   
    dx = x1 - x0
    dy = y1 - y0
    yi = 1

    if dy < 0: 
        yi = -1
        dy = -dy
    
    D = 2*dy - dx
    y = y0

    for x in range(x0,x1+1): 
        plotPoint(x,y,height,npim,pathedPoints,averagePathHeight,thicknessOffset)
        if D > 0: 
            y = y + yi
            D = D - 2*dx

        D = D + 2*dy




def plotLine(x0,y0,x1,y1,height,npim,pathedPoints,thicknessOffset):
    #pr(" plotLine")
    averagePathHeight = []

    if abs( y1-y0 ) < abs( x1-x0 ):
        if x0 > x1: 
             plotLineLow(x1,y1,x0,y0 ,height,npim,pathedPoints, averagePathHeight,thicknessOffset ) 
        else: 
             plotLineLow( x0,y0,x1,y1,height,npim,pathedPoints, averagePathHeight,thicknessOffset ) 
    else:
        if y0 > y1: 
            plotLineHigh(x1,y1,x0,y0,height,npim,pathedPoints, averagePathHeight,thicknessOffset )  
        else: 
            plotLineHigh( x0,y0,x1,y1,height,npim,pathedPoints, averagePathHeight,thicknessOffset )           
 



def plotPoint(x,y,height,npim,pathedPoints,averagePathHeight,thicknessOffset):
    plotY = y + thicknessOffset 
    plotX = x + thicknessOffset 
    pointKey = str(plotX) + "x" + str(plotY)  
    
    #pr("  plotting: {0}".format( pointKey ) )

    #Only update a point if we haven't already done something to it
    if pointKey not in pathedPoints: 
      

        # Smooth out heights by using an average of previous points on this line. 
        # This has the effect of paths getting too flat on steep aspects 
        if False:
            newHeight = height + npim[plotX][plotY]

            #Use average of last N heights. If this is too high, the flattening effect is worse
            numberOfAverageHeightsToUse = 5
            if len(averagePathHeight) > numberOfAverageHeightsToUse: 
                averagePathHeight.pop() 
        
            averagePathHeight.insert(0, newHeight )   
            npim[plotX][plotY] = sum(averagePathHeight) / len( averagePathHeight)  
            #pr("   using height: {0}".format(npim[plotX][plotY]) )
        else:
        #make thicker paths horizontally 'flat' by using the height from the primary line 
            if thicknessOffset == 0:
                newHeight = height + npim[x][y]
            else:
                #get the height from the primary line
                newHeight = npim[x][y]

            npim[plotX][plotY] = newHeight 
            #pr("   using height: {0}".format(npim[plotX][plotY]) )
       
        pathedPoints[ pointKey ] = True 
    else: 
        something = 0
        #pr("   skipped:")







# Add 1 or more GPX tracks to the model
#
# npim - The NumPy array that represents the elevation data
# dem - 
# importedGPX - Array of GPX file paths to be plotted
# gpxPathHeight - In meters, the height of the gpxPath. Negative number will show as a dent on the model
# trlat - top right latitude
# trlon - top right longitude
# bllat - bottom left latitude
# bllat - bottom left longitude 
#
# returns a modified numpy array of the elevation data
def addGPXToModel(pr,npim,dem,importedGPX,gpxPathHeight,gpxPixelsBetweenPoints,gpxPathThickness,trlat,trlon,bllat,bllon):
    import xml.etree.ElementTree as ET 
    import osr 
    import time 
    import math

    gpxStartTime = time.time()
    # Parse GPX file
    pathedPoints = {} 

    ulx, xres, xskew, uly, yskew, yres  = dem.GetGeoTransform()   

    target = osr.SpatialReference()
    target.ImportFromWkt( dem.GetProjection() ) 

    # This is WGS84
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326) 

    for gpxFile in importedGPX:
        pr("process gpx file: {0}".format( gpxFile ) )
        tree = ET.parse( gpxFile )
        root = tree.getroot() 
        points = root.find('{http://www.topografix.com/GPX/1/1}trk/{http://www.topografix.com/GPX/1/1}trkseg') 

        # We need to keep track of the last point so that we can draw a line between points
        lastPoint = None       


       
        count = 0 

        for trkpt in points:

            count = count + 1
             
           

            gpx_lat = float( trkpt.attrib['lat'] )
            gpx_lon = float( trkpt.attrib['lon'] ) 
            #pr("Lat: {0} Lon: {1}:".format( gpx_lat, gpx_lon ) ) 

            
            #if gpx_lat < trlat and gpx_lat > bllat and gpx_lon < trlon and gpx_lon > bllon: 
            transform = osr.CoordinateTransformation(source,target ) 
            projectedPoints = transform.TransformPoint(gpx_lat, gpx_lon) 
 
            rasterX = int( (projectedPoints[1] - uly) / yres )   
            rasterY = int( (projectedPoints[0] - ulx) / xres )   
            
            # Only process this point if it's in the bounds
            if rasterX >= 0 and rasterX < npim.shape[0] and rasterY >=0 and rasterY < npim.shape[1]:
                
                currentPoint = (rasterX,rasterY) 

         
                #plotPoint( currentPoint[0],currentPoint[1],gpxPathHeight+300,npim,pathedPoints,averagePathHeight ) 
                              
                #Draw line between two points using Bresenham's line algorithm 
                if lastPoint is not None: 
                    #calculate distance between last point and current point 
                    #Only plot the point if it's far away. Helps cull some GPX points
                    dist = math.sqrt((rasterX - lastPoint[0])**2 + (rasterY - lastPoint[1])**2) 

                    # Only render the GPX point if it's beyond the specified distance OR
                    # if it's the last point
                    if dist >= gpxPixelsBetweenPoints or count == len(points) -1: 
                        #try creating a dashed path by plotting every other line
                       
                        #pr("primaryLine")
                        plotLine(lastPoint[0],lastPoint[1],currentPoint[0],currentPoint[1],gpxPathHeight,npim,pathedPoints,0) 

                        #create line thickness by stacking lines
                        thicknessOffset = 1 
                      
                        for loopy in range(1, int(gpxPathThickness) ):
                            
                            #pr("thickerLine")
                      
                            plotLine(lastPoint[0],lastPoint[1],currentPoint[0],currentPoint[1],gpxPathHeight,npim,pathedPoints,thicknessOffset) 

                            #alternate sides of line to draw on when adding 
                            #thickness
                            if (loopy % 2) == 0: 
                                thicknessOffset = (thicknessOffset * -1) + 1    
                            else:
                                thicknessOffset = thicknessOffset * -1    
                                
                            

                        lastPoint = currentPoint
                else:
                    lastPoint = currentPoint 
            else:
                #if a point is out of bounds, we need to invalidate lastPoint
                lastPoint = None

    gpxEndTime = time.time()
    gpxElapsedTime = gpxEndTime - gpxStartTime
    pr("Time to add GPX paths:{0}".format( gpxElapsedTime ) )
     


