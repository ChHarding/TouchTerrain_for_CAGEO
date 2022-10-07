## EarthEngine Authentication Guide
Aug.25, 2022
Chris Harding (charding@iastate.edu)

This guide is only relevant for those who want to:

  a) run the standalone version of TouchTerrain in a binder jupyter notebook and

  b) want to use it with online elevation data (via Google Earth Engine) instead of only with local geotiff files

<div>

#### Rationale
- Using the colab badge [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](http://colab.research.google.com/github/ChHarding/TouchTerrain_for_CAGEO/blob/master/TouchTerrain_jupyter_starters_colab.ipynb) or the binder badge [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/ChHarding/TouchTerrain_for_CAGEO/HEAD?labpath=TouchTerrain_jupyter_starters_binder.ipynb) will eventually show you a notebook (TouchTerrain_jupyter_starters_binder.ipynb) inside a browser.
- When running the cell `ee.Authenticate()` in this notebook, you will be required to generate and paste in a token (code) that connects your notebook code with a EarthEngine dev account
  
  
#### Request a EarthEngine dev account  (I'm actually not sure if this is required, so you could skip this part and see if the rest works!)
- This assumes that you have a standard Google account and are signed in with it on your current browser
- In your browser, go to go to https://signup.earthengine.google.com/ and request an account
- Use something like `Want to use TouchTerrain to create 3D printable terrain models` files as reason
- I think this will only work for private and research usage, so use this for Organization/Institution
- You should get an email with sign-up intructions __(need more detail for this part, which I cannot do myself!)__
  
#### Generating the token
- Running `ee.Authenticate()` will output a URL (starting with https://code.earthengine.google.com/), click on it
- You should see the Google Earth Engine Notebook Authenticator page:
![Notebookauthenticator](https://user-images.githubusercontent.com/19935989/186751910-ba84b6bf-bcb7-4334-a8c7-b7d57bf367f8.PNG)
- Select Read-only and click on Choose Project
- Click on Create new Cloud project and fill in the id (which has to be unique!) and name fields, then click Select
![Choose_project](https://user-images.githubusercontent.com/19935989/186755046-61eacad6-847b-43db-8905-535a8490acbf.PNG)
- Back on the Notebook Authenticator page you should now see the newly created project as Cloud project
- Click on Generate Token below it.
- Choose a Google account (this should be the same that you are already logged in with)
- Go through this warning (Click Continue)
![Unverified](https://user-images.githubusercontent.com/19935989/186753217-0c62cefc-5dcd-4ab4-a03c-0361128ea32b.PNG)
  
- Then grant your Earth Engine Notebook access (I checked both EarthEngine and Cloudstorage but I'm not sure if the second is actually needed ...)
  
![WantsAccess](https://user-images.githubusercontent.com/19935989/186753654-6bda55e6-f2e8-4cfc-89ac-b9361552806f.PNG)

- Finally, get your token (will be in the orange box in this image). Click on the icon to the right of it to copy it.
![Token](https://user-images.githubusercontent.com/19935989/186754341-486105c4-c467-4f70-8c00-04f64e165c0d.PNG)
  
- Return to your notebook, paste (Control-V) your token into the entry box and hit Enter/Return(!)
- You should see: `Successfully saved authorization token.`
- You can now use EarthEngine data to generate 3D terrain models! Continue with the next cell in the notebook.

