# -*- coding: utf-8 -*-
#
#    create_imgtdb.py
#    Copyright (c) 2017 Be The Match operated by National Marrow Donor Program. All Rights Reserved.
#
#    This library is free software; you can redistribute it and/or modify it
#    under the terms of the GNU Lesser General Public License as published
#    by the Free Software Foundation; either version 3 of the License, or (at
#    your option) any later version.
#
#    This library is distributed in the hope that it will be useful, but WITHOUT
#    ANY WARRANTY; with out even the implied warranty of MERCHANTABILITY or
#    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
#    License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this library;  if not, write to the Free Software Foundation,
#    Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA.
#
#    > http://www.fsf.org/licensing/licenses/lgpl.html
#    > http://www.opensource.org/licenses/lgpl-license.php
#

import argparse
import json
import logging
import os
import re
import sys
import urllib.request

from Bio import SeqIO
from BioSQL import BioSeqDatabase

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    stream=sys.stdout,
                    level=logging.INFO)


def get_imgt_versions():
    """IMGT Databases are releases as branches of IMGTHLA repo in GitHub.
    We'll get the names of all the branches with numeric values and
    return the list sorted in descending order.
    """
    imgt_branches_api_url = 'https://api.github.com/repos/ANHIG/IMGTHLA/branches?per_page=100'
    response_json = json.load(urllib.request.urlopen(imgt_branches_api_url))
    all_db_versions = [int(branch['name']) for branch in response_json if branch['name'].isdigit()]
    all_db_versions.sort(reverse=True)
    return all_db_versions


def download_dat(db):
    url = 'https://media.githubusercontent.com/media/ANHIG/IMGTHLA/' + db + '/hla.dat'
    url = 'https://raw.githubusercontent.com/ANHIG/IMGTHLA/' + db + '/hla.dat'
    dat = ".".join([db, "hla", "dat"])
    urllib.request.urlretrieve(url, dat)
    return dat


def download_allelelist(db):
    url = 'https://raw.githubusercontent.com/ANHIG/IMGTHLA/Latest/Allelelist.' + db + '.txt'
    alist = ".".join([db, "Allelelist", "txt"])
    urllib.request.urlretrieve(url, alist)
    return alist


def main():
    """This is run if file is directly executed, but not if imported as
    module. Having this in a separate function  allows importing the file
    into interactive python, and still able to execute the
    function for testing"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose",
                        help="Option for running in verbose",
                        action='store_true')

    parser.add_argument("-n", "--number",
                        required=False,
                        help="Number of IMGT/DB releases",
                        default=1,
                        type=int)

    parser.add_argument("-r", "--releases",
                        required=False,
                        help="IMGT/DB releases",
                        type=str)

    args = parser.parse_args()
    releases = args.releases
    number = args.number

    if args.verbose:
        verbose = True
    else:
        verbose = False

    if releases:
        dblist = [db for db in releases.split(",")]
    else:
        dblist = map(str, get_imgt_versions()[:number])  # get the last n releases

    # Connecting to mysql DB
    server = BioSeqDatabase.open_database(driver="pymysql", user="root",
                                          passwd="", host="0.0.0.0",
                                          db="bioseqdb")

    if verbose:
        logging.info("IMGT/HLA DB Versions = " + ",".join(dblist))

    # Looping through DB verions
    for dbv in dblist:

        # Downloading hla.dat file
        hladat = download_dat(dbv)

        if verbose:
            logging.info("Finished downloading hla.dat file for " + str(dbv))

        # Downloading allele list
        allele_list = download_allelelist(dbv)

        if verbose:
            logging.info("Finished downloading allele list for " + str(dbv))

        hla_names = {}
        try:
            # File formats change...
            with open(allele_list, 'r') as f:
                for line in f:
                    line = line.rstrip()
                    if re.search("#", line) or re.search("AlleleID", line):
                        continue
                    accession, name = line.split(",")
                    hla_names.update({accession: name})
            if verbose:
                nalleles = len(hla_names.keys())
                logging.info("Finished loading " + str(nalleles)
                             + " alleles for " + str(dbv))
        except ValueError as err:
            list_error = "Allelelist error: {0}".format(err)
            logging.error(list_error)
            server.close()
            os.remove(hladat)
            os.remove(allele_list)
            sys.exit()

        # Loading sequence data from hla.dat file
        try:
            seq_list = SeqIO.parse(hladat, "imgt")
        except:
            # read_error = "Read dat error: {0}".format(err)
            logging.error("ERROR LOADING!!")
            server.close()
            os.remove(hladat)
            os.remove(allele_list)
            sys.exit()

        new_seqs = {"A": [], "B": [], "C": [], "DRB1": [],
                    "DQB1": [], "DRB3": [], "DRB4": [], "DRB5": [],
                    "DQA1": [], "DPA1": [], "DPB1": []}

        # Changing the sequence name to
        # the HLA allele name instead of the accession
        for seq in seq_list:
            if seq.name in hla_names:
                loc, allele = hla_names[seq.name].split("*")
                if loc in new_seqs:
                    hla_name = "HLA-" + hla_names[seq.name]
                    seq.name = hla_name
                    new_seqs[loc].append(seq)

        dbsp = list(dbv)
        descr = ".".join([dbsp[0], dbsp[1] + dbsp[2], dbsp[3]])

        if verbose:
            logging.info("Loaded IMGT dat file " + descr)

        # Looping through and loading each locus
        for locus in new_seqs:
            dbname = dbv + "_" + locus
            dbdescription = "IMGT/HLA " + descr + " " + locus
            db = server.new_database(dbname, description=dbdescription)
            try:
                count = db.load(new_seqs[locus])
            except:
                load_fail = sys.exc_info()[0]
                logging.error("Failed to load " + load_fail)
                server.close()
                os.remove(hladat)
                os.remove(allele_list)
                sys.exit()

            if verbose:
                logging.info("Loaded " + str(count) + " for " + dbname)

            # Committing data to mysql db
            server.commit()

        # Removing hla.dat and allele list files
        os.remove(hladat)
        os.remove(allele_list)

        if verbose:
            logging.info("Finished loading " + descr)

    server.close()


if __name__ == '__main__':
    """The following will be run if file is executed directly,
    but not if imported as a module"""
    main()
