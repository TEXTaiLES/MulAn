# Changes TBI

- This is a research-oriented tool, not a commercial one. Restructure the text descriptions throughout to match the expected style (eg, change "MulAn keeps every spectral band and semantic class exactly where it belongs" too corny). Convert the "Convert. Inspect. Annotate" in the main page to "MulAn: Multipsectral Image Viewer and Annotator". Simplify all such cases.
- Change the general color palette from red to a pastel purple.
- In the converter, add an arrow to the left of the channel list indicating ascending light bandwidth. The goal of this is to clearly state where to put lower and higher nms images.
- The image frame in the multispectral viewer (single channel view) is too large - make the size smaller (zoom in/out functions exist anyway). The annotator frame size is good. 
- In the converter, it is likely (in my use cases) that I upload images named 600.bmp, 700bmp, rgb.bmp etc. When the name includes indications like 700, 700nm, wavelength_700 etc, automatically assign it the corresponding name, in this case 700nm. Do this on image upload every time a new image is added.
- In the annotator, allow the use of shortcuts for each tool. Add on-hover indicators that show the shortcut for each tool.
- In the annotator, remove the pixel count in the layers - it's unnecessary.
- In the annotator, the "move class up/down" buttons are pretty random - replace them with simple arrow up/down icons. 
- In the annotator, allow undoing/redoing the mask apply.
- In the annotator, the warning popup should go away after a couple of seconds.