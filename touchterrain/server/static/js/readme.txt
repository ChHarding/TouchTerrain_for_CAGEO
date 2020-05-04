
CH Note:

as for my models the z and y are switched, I hacked stl_viewer.min.js so that in the the positions for its lights, z and y are also switched.  


Stl Viewer v1.06
================

Installation:
-------------
upload those files into your web server:
stl_viewer.min.js 
parser.min.js 
load_stl.min.js 
webgl_detector.js 
CanvasRenderer.js 
OrbitControls.js 
Projector.js 
three.min.js


Usage:
------
At the html body:

<script src="stl_viewer.min.js"></script>
<div id="stl_cont"></div>
<script>
	var stl_viewer=new StlViewer(document.getElementById("stl_cont"), { models: [ {id:0, filename:"mystl.stl"} ] });
</script>



Documentation & License details:
--------------------------------
https://www.viewstl.com/plugin/



by Omri Rips, Viewstl.com
