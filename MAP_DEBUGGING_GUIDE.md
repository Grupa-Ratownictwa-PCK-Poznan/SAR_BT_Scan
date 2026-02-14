# Map Rendering Debugging Guide

If the heatmap is still not displaying points, follow these steps to diagnose the issue:

## Step 1: Open Browser Developer Tools
1. Open the web UI in your browser
2. Press **F12** or **Ctrl+Shift+I** (Windows/Linux) or **Cmd+Option+I** (macOS)
3. Click on the **Console** tab

## Step 2: Check for JavaScript Errors
1. Look for any red error messages in the console
2. Take note of any errors that appear - they may indicate:
   - Missing libraries (Leaflet, Leaflet.heat)
   - Network errors fetching the API
   - Runtime errors in the map code

## Step 3: Verify Library Loading
The console should show messages like:
```
API_BASE: http://localhost:8000
Leaflet library URL: checking if loaded...
L object available: true
L.heatLayer available: true
```

If `L object available: false`, Leaflet didn't load.
If `L.heatLayer available: false`, the heat.js library didn't load.

## Step 4: Check Map Initialization
When the page loads, you should see:
```
Initializing map...
Map container found, size: XXXXX x XXXXX
Leaflet library available
Map object created
OSM tiles added to map
Map size invalidated
Initial heatmap update called
```

If you see `Map container not found`, the map div is missing or hidden.

## Step 5: Verify API Data
The console should show:
```
Fetching heatmap from: http://localhost:8000/api/map/heatmap?...
Heatmap data received: N points
```

If it says "0 points", check your database has GPS data. The API should return the raw points response showing latitude/longitude values.

## Step 6: Monitor Heatmap Rendering
Look for:
```
Creating heat layer with N points
Sample point: [52.431550833, 16.943841667, 0.6]
Heat layer created and added to map
Map fitted to bounds: LatLngBounds
```

Or if using fallback:
```
L.heatLayer is not defined - heat.js library may not be loaded
Using fallback circle marker rendering...
Rendered fallback heatmap with circle markers...
Created N circle markers
```

## Common Issues & Solutions

### Issue: "L object available: false"
**Solution**: Leaflet library didn't load from CDN
- Check network tab for failed requests to cdnjs
- Try refreshing the page
- Check if cdnjs.cloudflare.com is accessible from your network

### Issue: "L.heatLayer available: false"
**Solution**: Leaflet.heat library didn't load
- The app will automatically fall back to circle markers
- Check network tab for "leaflet-heat.min.js" request
- This should not prevent points from showing (fallback renders circles)

### Issue: Map shows but no points visible
**Possibilities**:
1. **No GPS data in database**: Check if you have WiFi associations or BT sightings with GPS coordinates
2. **Map not fitted to bounds**: The map might be showing the default center (London) instead of your data
3. **Points outside current view**: Pan/zoom the map to find them
4. **API returning wrong data**: Check `/api/map/heatmap` endpoint directly in browser

### Issue: "Map container not found"
**Solution**: The map div isn't rendering
- Check if page is fully loaded (wait for all elements to render)
- Check CSS for display:none or visibility:hidden on map element
- Try refreshing page

## Testing the API Directly

Open this URL in your browser to see raw API response:
```
http://localhost:8000/api/map/heatmap
```

It should return JSON like:
```json
{
  "points": [
    {"lat": 52.431550833, "lon": 16.943841667, "rssi": -40, "intensity": 0.6, "type": "wifi"},
    ...
  ]
}
```

If empty points array `[]`, you may need GPS data in your database.

## Forcing Fallback Rendering

If the issue is specifically with heat.js library:
1. Open Developer Tools
2. Run in Console: `L.heatLayer = null;`
3. Refresh page
4. It should now render circle markers as fallback

## Still Not Working?

If you've checked all above and still see no points:

1. **Copy all console output and error messages**
2. **Check that your browser's Network tab shows**:
   - ✅ leaflet.min.js loaded successfully
   - ✅ leaflet-heat.min.js loaded successfully (or fallback used)
   - ✅ `/api/map/heatmap` request returns data with points

3. **Share**:
   - Your database file location and number of records
   - Browser developer console screenshot showing any errors
   - Network tab screenshot from F12 tools
   - Your server logs showing the `/api/map/heatmap` request

## Expected Behavior

Once working, you should see:
1. **Map container** with OpenStreetMap tiles displaying
2. **Heat layer** or **circle markers** showing GPS points
3. **Zoom out** to see all points in your region
4. **Click a point** to see details (if using fallback circles)
5. **Filter controls** refining which points display (left sidebar)
