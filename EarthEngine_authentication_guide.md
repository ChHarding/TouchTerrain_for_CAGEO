## EarthEngine Authentication Guide
Aug.25, 2022
Chris Harding (charding@iastate.edu)

This guide is only relevant for those who want to:

a) run the standalone version of TouchTerrain in a binder jupyter notebook

b) want to use it with online elevation data (via Google Earth Engine) instead of using local geotiff files

<div>
  
### 
- Using the Run on Binder badge will eventually show you a notebook (TouchTerrain_jupyter_starters_binder.ipynb) inside a browswer
- When running the cell `ee.Authenticate()` in this notebook you will be required to generate a token (code) that connects your notebook code with a EarthEngine dev account
- I will walk you through the required steps
  
  
#### Request a EarthEngine dev account
- This assumes that you have a standard Google account and are signed in on your browser
- Go to go to https://signup.earthengine.google.com/ and request an account
- Use something like `Want to use TouchTerrain to create terrain model` files as reason
- I think this will only work for private and research usage, so use this for Organization/Institution
- You should get an email with sign-up intructions __(need more detail!)__
  
#### Generating the token
- 
