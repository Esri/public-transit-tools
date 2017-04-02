################################################################################
# sqlize_csv.py, originally written by Luitien Pan
# Last updated 6 October 2016 by Melinda Morang, Esri
################################################################################
'''Copyright 2016 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''
################################################################################
# Imports the CSV-formatted GTFS information into a SQLite database file.
# Handles data conversion, table creation, and indexing transparently.
#
# If you specify multiple GTFS datasets, this merges them.  In order to avoid
# collisions between identifiers that are supposed to be dataset-unique, I
# prepend an agency label to each *_id field value.  This label comes from the
# last component of the corresponding GTFS_DIR* path.  So for example, if I
# keep my CTA data in
#   /home/luitien/gtfs/cta/*.txt
# then stop_id 1518 gets stored and manipulated as "cta:1518".
#
# In line with this, *don't* put your CSV files like so:
#   [...]/cta/data/*.txt
#   [...]/metra/data/*.txt
# and so on, because then they'll all be labelled as ``data''.

import csv
import datetime
import itertools
import os
import re
import sqlite3
import sys

class CustomError(Exception):
    pass

ispy3 = sys.version_info >= (3, 0)

Errors_To_Return = []
populate_route_info = True

csv_fnames = ["trips.txt", "routes.txt", "shapes.txt"]


sql_types = {
        str :   "TEXT" ,
        float : "REAL" ,
        int :   "INTEGER" ,
    }
# Each subdictionary specifies the columns for the named sql table.
# The format is:
#   tbl_name : { col_name : (datatype, is_required) }
# where is_required is True for columns required by the GTFS
#                   and names the default value otherwise.
sql_schema = {
        "trips" : {
                "route_id" :    (str, True) ,
                "service_id" :  (str, True) ,
                "trip_id" :     (str, True) ,
                "trip_headsign" :   (str, "NULL") ,
                "trip_short_name" :     (str, "NULL") ,
                "direction_id" : (int, "NULL") ,
                "block_id" :    (str, "NULL") ,
                "shape_id" :    (str, "NULL") ,
            } ,
        "routes" : {
                "route_id" :    (str, True),
                "agency_id" :  (str, "NULL"),
                "route_short_name": (str, True),
                "route_long_name":  (str, True),
                "route_desc":   (str, "NULL"),
                "route_type":   (int, True),
                "route_url":    (str, "NULL"),
                "route_color":  (str, "NULL"),
                "route_text_color": (str, "NULL")
            } ,
        "shapes" : {
                "shape_id":     (str, True),
                "shape_pt_lat": (float, True),
                "shape_pt_lon": (float, True),
                "shape_pt_sequence":    (int, True),
                "shape_dist_traveled":  (float, "NULL")
            }
    }

db = None

def connect(dbname):
    global db
    db = sqlite3.connect(dbname)

def make_remove_extra_fields(tablename, columns):
    '''Make a function that removes extraneous columns from the CSV rows.
    E.g.: the CTA dataset has things like stops.wheelchair_boarding and
    trips.direction that aren't in the spec.'''
    orig_num_fields = len(columns)
    # Identify the extraneous columns:
    cols = [ ]
    tbl = sql_schema[tablename]
    for idx,field in enumerate(columns):
        if field not in tbl:
            cols.append(idx)
    cols.reverse()
    # ... and here's the function:
    def drop_fields(in_row):
        out_row = list(in_row)
        # Check that row was the correct length in the first place.
        if len(out_row) != orig_num_fields:
            msg = "GTFS table %s contains at least one row with the wrong number of fields. Fields: %s; Row: %s" % (tablename, columns, str(in_row))
            Errors_To_Return.append(msg)
            raise CustomError
        # Remove the row entries for the extraneous columns
        for idx in cols:
            out_row.pop(idx)
        return tuple(out_row)
    return drop_fields


def check_for_required_fields(tablename, columns, dataset):
    '''Check that the GTFS file has the required fields'''
    for col in sql_schema[tablename]:
        if sql_schema[tablename][col][1] == True:
            if not col in columns:
                msg = "GTFS file " + tablename + ".txt in dataset " + dataset + " is missing required field '" + col + "'. Failed to SQLize GTFS data"
                Errors_To_Return.append(msg)
                raise CustomError


def check_latlon_fields(rows, col_names, fname):
    '''Ensure lat/lon fields are valid'''
    def check_latlon_cols(row):
        shape_id = row[col_names.index("shape_id")]
        shape_pt_sequence = row[col_names.index("shape_pt_sequence")]
        lat = row[col_names.index("shape_pt_lat")]
        lon = row[col_names.index("shape_pt_lon")]
        try:
            lat_float = float(lat)
        except ValueError:
            msg = 'The point sequence "%s" in shape_id "%s" in %s contains an \
invalid non-numerical values \
for the shape_pt_lat field: "%s". Please double-check all lat/lon values in your \
shapes.txt file.' % (shape_pt_sequence, shape_id, fname, lat)
            Errors_To_Return.append(msg)
            raise CustomError
        try:
            lon_float = float(lon)
        except ValueError:
            msg = 'The point sequence "%s" in shape_id "%s" in %s contains an \
invalid non-numerical values \
for the shape_pt_lon field: "%s". Please double-check all lat/lon values in your \
shapes.txt file.' % (shape_pt_sequence, shape_id, fname, lon)
            Errors_To_Return.append(msg)
            raise CustomError
        if not (-90.0 <= lat_float <= 90.0):
            msg = 'The point with sequence "%s" in shape_id "%s" in %s contains an invalid value outside the \
range (-90, 90) the shape_pt_lat field: "%s". shape_pt_lat values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your shapes.txt file.\
' % (shape_pt_sequence, shape_id, fname, lat)
            Errors_To_Return.append(msg)
            raise CustomError
        if not (-180.0 <= lon_float <= 180.0):
            msg = 'The point with sequence "%s" in shape_id "%s" in %s contains an invalid value outside the \
range (-180, 180) the shape_pt_lon field: "%s". shape_pt_lon values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your shapes.txt file.\
' % (shape_pt_sequence, shape_id, fname, lon)
            Errors_To_Return.append(msg)
            raise CustomError
        return row
    if ispy3:
        return map(check_latlon_cols, rows)
    else:
        return itertools.imap(check_latlon_cols, rows)


def column_specs(tablename):
    '''Turns the sql_schema python datastructure above into the appropriate
    column specs for a CREATE TABLE statement.  Used in create_table().'''
    tblspec = sql_schema[tablename]
    lines = [ "id   INTEGER PRIMARY KEY" ]
    for col_name in tblspec:
        col_type,required = tblspec[col_name]
        data_type = sql_types[col_type]
        if required is True:
            defaults_str = ""
        else:
            defaults_str = " DEFAULT %s" % required
        lines.append ("%s\t%s%s" % (col_name, data_type, defaults_str))
    return " ,\n".join (lines)


def create_table(tablename):
    db.execute("DROP TABLE IF EXISTS %s;" % tablename)
    create_stmt = "CREATE TABLE %s (%s);" % (tablename, column_specs(tablename))
    db.execute(create_stmt)
    db.commit()


def handle_file(fname, service_label):
    '''Creates and populates a table for the given CSV file.'''

    if fname.endswith(".txt"):
        tablename = fname[:-4]
    else:
        tablename = fname
    tablename = os.path.basename(tablename)

    #-- Read in everything from the CSV table
    if ispy3:
        f = open(fname, encoding="utf-8-sig")
    else:
        f = open(fname)
    reader = csv.reader(f)
    # Put everything in utf-8 to handle BOMs and weird characters.
    # Eliminate blank rows (extra newlines) while we're at it.
    if ispy3:
        reader = ([x.strip() for x in r] for r in reader if len(r) > 0)
    else:
        reader = ([x.decode('utf-8-sig').strip() for x in r] for r in reader if len(r) > 0)

    # First row is column names:
    columns = [name.strip() for name in next(reader)]

    #-- Do some data validity checking and reformatting
    # Check that all required fields are present
    check_for_required_fields(tablename, columns, service_label)
    # Make sure lat/lon values are valid
    if tablename == "trips":
        # If trips has no shape_id column, we can't populate route info in the output,
        # but we can still draw the shapes in the map.
        if "shape_id" not in columns:
            global populate_route_info
            populate_route_info = False
    if tablename == "shapes":
        rows = check_latlon_fields(reader, columns, fname)
    # Otherwise just leave them as they are
    
    else:
        rows = reader
    # Prepare functions for filtering out unrequired columns
    columns_filter = make_remove_extra_fields(tablename, columns)
    # Remove unnecessary columns
    columns = columns_filter(columns)
    # Remove columns that aren't in the spec:
    if ispy3:
        rows = map(columns_filter, rows)
    else:
        rows = itertools.imap(columns_filter, rows)

    # Add to the SQL table
    values_placeholders = ["?"] * len(columns)
    cur = db.cursor()
    cur.executemany("INSERT INTO %s (%s) VALUES (%s);" %
                        (tablename,
                        ",".join(columns),
                        ",".join(values_placeholders))
                        , rows)
    db.commit()
    cur.close()
    f.close()


def handle_agency(gtfs_dir):
    '''Parses the relevant parts of an agency's GTFS CSV files into
    the sqlite database. Returns a list of error messages from some basic
    GTFS dataset validation'''

    try:
        csvs_withPaths = []
        # Create a dataset label
        label = os.path.basename(os.path.normpath(gtfs_dir))

        # Verify that the required files are present
        missing_files = []
        has_a_calendar = 0
        for fname in csv_fnames:
            fname2 = os.path.join(gtfs_dir, fname)
            if os.path.exists(fname2):
                csvs_withPaths.append(fname2)
            else:
                missing_files.append(fname)
        if missing_files:
            Errors_To_Return.append("GTFS dataset %s is missing files required for \
    this tool: %s" % (label, str(missing_files)))
            return Errors_To_Return

        # Sqlize each GTFS file
        for fname2 in csvs_withPaths:
            handle_file(fname2, label)

        # Return any errors we collected, or an empty list if there were none.
        return Errors_To_Return

    except UnicodeDecodeError:
        Errors_To_Return.append(u"Unicode decoding of GTFS dataset %s failed. Please \
ensure that your GTFS files have the proper utf-8 encoding required by the GTFS \
specification." % label)
        return Errors_To_Return
    except CustomError:
        return Errors_To_Return
    except:
        raise


def create_indices():
    cur = db.cursor()
    cur.execute("CREATE INDEX trips_index_shapes ON trips (shape_id);")
    cur.execute("CREATE INDEX shapes_index_shapes ON shapes (shape_id);")
    db.commit()
    cur.close()


def metadata():
    db.execute("DROP TABLE IF EXISTS metadata;")
    db.execute("CREATE TABLE metadata (key TEXT, value TEXT);")
    db.execute("""INSERT INTO metadata (key, value) VALUES ("timestamp", ?);""", (datetime.datetime.now().isoformat(),))
    db.commit()

def main(argv):
    argv = argv[1:]  # make local copy
    dbname = argv.pop(0)
    connect(dbname)
    for tblname in sql_schema:
        create_table(tblname)
    for gtfs_dir in argv:
        handle_agency(gtfs_dir)
    print >>sys.stderr, "Creating indices..."
    create_indices()
    metadata()
    return 0

if __name__ == '__main__':
    sys.exit(main (sys.argv))
