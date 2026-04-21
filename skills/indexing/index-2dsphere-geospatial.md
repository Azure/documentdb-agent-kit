# index-2dsphere-geospatial

**Category:** Indexing · **Priority:** MEDIUM

## Why it matters

For location queries — "stores near me", "points inside this polygon", "does this route intersect this region?" — use a **`2dsphere`** index over **GeoJSON** values. `2dsphere` supports earth-like sphere geometry (correct across longitudes, near poles, etc.); the older `2d` index type treats coordinates as flat and is generally not what you want.

The most common mistake is the coordinate order: **GeoJSON is `[longitude, latitude]`**, not `[lat, lng]`. Every time.

## Incorrect

`[latitude, longitude]` order — silently wrong, returns nonsense results:

```javascript
db.stores.insertOne({
  name: "Downtown",
  location: { type: "Point", coordinates: [47.6062, -122.3321] }  // lat, lng — WRONG
});
db.stores.createIndex({ location: "2dsphere" });
db.stores.find({ location: { $near: { $geometry: { type: "Point", coordinates: [47.6062, -122.3321] }, $maxDistance: 5000 } } });
// No results (or nonsensical ones). The point is actually off the coast of
// Antarctica because lng=47, lat=-122 is invalid latitude.
```

Storing plain `[x, y]` numbers without the GeoJSON envelope:

```javascript
db.stores.insertOne({ name: "Downtown", location: [-122.3321, 47.6062] });
db.stores.createIndex({ location: "2dsphere" });
// 2dsphere expects a GeoJSON object, not a bare array. $near won't work.
```

## Correct

Store GeoJSON, `[longitude, latitude]` order, with a `2dsphere` index:

```javascript
db.stores.insertOne({
  name: "Downtown",
  location: {
    type: "Point",
    coordinates: [-122.3321, 47.6062]   // [lng, lat]
  }
});

db.stores.createIndex({ location: "2dsphere" });

// Nearest stores within 5 km of the user's point
db.stores.find({
  location: {
    $near: {
      $geometry: { type: "Point", coordinates: [-122.3321, 47.6062] },
      $maxDistance: 5000   // meters
    }
  }
});

// Stores inside a polygon
db.stores.find({
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [-122.35, 47.60], [-122.30, 47.60],
          [-122.30, 47.62], [-122.35, 47.62],
          [-122.35, 47.60]
        ]]
      }
    }
  }
});
```

`2dsphere` also supports `LineString`, `MultiPoint`, `MultiPolygon`, `GeometryCollection`, and `$geoIntersects`.

**Compound `2dsphere` indexes** are allowed and useful — put the geospatial field last so equality/range filters narrow the result set before the geometry check:

```javascript
db.stores.createIndex({ category: 1, location: "2dsphere" });
db.stores.find({
  category: "coffee",
  location: { $near: { ... } }
});
```

## References

- [MongoDB `2dsphere` indexes](https://www.mongodb.com/docs/manual/core/2dsphere/)
- [GeoJSON spec](https://geojson.org/) — always `[longitude, latitude]`
