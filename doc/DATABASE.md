# DATA MODEL

## Dimensional Modelling

The data model follows the [dimensional modelling]
(https://en.wikipedia.org/wiki/Dimensional_modeling) approach by Ralph Kimball. 
More references can also be found in [Star Schemas](https://en.wikipedia.org/wiki/Star_schema).

## The data model

The figure below shows the layout of **tessdb**.

![TESS Database Model](tessdb-full.png)

### Dimension Tables

* `date_t`      : preloaded from 2016 to 2026
* `time_t`      : preloaded, with minute resolution
* `tess_t`: registered TESS instruments collecting data
* `location_t`  : locations where instruments are deployed
* `tess_units_t`     : an assorted collection of unit labels for reports, preloaded with current units.

#### Instrument Dimension

This dimension holds the current list of TESS instruments. 

* The real key is an artificial key `tess_id` linked to the Fact table.
* The `mac_address` could be the natural key if it weren't for the calibration constant history tracking.
* The `name` attribute could be an alternative key for the same reason. TESS instruments send readings using this name.
* A TESS instrument name can be changed as long as there is no other instrument with the same name.
* The `location_id` is a reference to the current location assigned to the instrument.
* Location id -1 denotes the "Unknown" location.
* The `calibration_k` holds the current value of the instrument calibration constant.
* A history of calibration constant changes are maintained in the `tess_t` table if the instrument is ever recalibrated. 
* Columns `calibrated_since` and `calibrated_until`hold the timestamps where the calibration constant is valid. 
* Column `calibrated_state` is an indicator. Its values are either **`Current`** or **`Expired`**. 
* The current calibration constant has its indicator set to `Current` and the expiration date in a far away future (Y2999).

#### Unit dimension

The `tess_units_t` table is what Dr. Kimball denotes as a *junk dimension*. It collects various labels denoting
the current measurement units of samples in the fact table. 

* Columns `valid_since`, `valid_until` and `valid_state` keep track of units change in a similar technique as above should the units change.

### Fact Tables

* `tess_readings_t` : Accumulating snapshot fact table containing measurements from several TESS instruments.

TESS devices with accelerometer will send `azimuth` and `altitude` values, otherwise they are `NULL`.
TESS devices with a GPS will send `longitude`, `latitude` and `height` values, otherwise they are `NULL`.

## Sample queries

TBD

