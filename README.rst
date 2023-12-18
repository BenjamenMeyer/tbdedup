TBDedup
=======

TBDedup is a Mail De-duplication program for Thunderbird MBOX files.

History
-------

TBDedup was born out of trying to figure out how fix my massive amounts of email after
having an issue where the Inbox of my Local Mail folder got copied into itself and it
managed to do so 18 or 19 times before I manually killed Thunderbird. Since email
was being processed during that time I no longer knew which folders I could trust
and which I could not. Some of my folders contain years of archives of mail lists and
other activities so I wanted to keep them around. However, Thunderbird did not offer
any tools for deduplicating the email.

I did find one Deduplication Extension (https://addons.thunderbird.net/en-US/thunderbird/addon/removedupes/)
however, it ran had limits due to how it interacts with Thunderbird and some of my
larger emails folders would crash out on it. This lead to me needing to manually consolidate
folders and then using the extension in localized sets to deduplicate data within its
limits, but still did not solve the large folder issue.

For reference, some of the folders contained a half-million or more messages before
being consolidated. One folder imparticular ended up having about 4.3 million records
after being consolidated with a disk footprint of 33 GB. Thunderbird itself would time
out trying to generate the MSF index files it uses for quick access, let alone trying to
run a deduplication tool on it.

As a result, I needed a tool I could offline, outside of Thunderbird where I could control
the functionality and be limited only by the capabilities of my computer.

Thus TBDedup was born. In the process I tried out two primary variations and thought of
looking into another. One variation was developed in Go (https://github.com/BenjamenMeyer/go-tb-dedup);
however, while it could process records quickly it ran into limitations and processing the file
took too many resources - using over 1 GB of RAM and taking an extremely long time as basic
testing would run overnight due to the nature of Go. After replicating the functionality in Python
and having far smaller test times and usage of 40 MB I decided to keep the Python version.

How it works
------------

TBDedup walks a directory tree and finds any file that it can read using the MBOX file format.
It then tries to identify which MBOX File Format is in use as part of deciding if the file
can be processed. If it cannot read the file it logs it and continues on. This process is done
asynchronously so the directory tree is walked quickly.

When a file is identified it then splits out another Async task to process just that file.
The new task will then syncrhonously read each message out of the file, parsing the data,
and recording the file start and end offsets of the message. It then calculates the SHA hashes
of both the disk data (recreated in memory) and the parsed data without the MBOX FROM line
and stores all the information into a SQLite database.

Once all the files are processed, then the it checks the database for the unique records based
on the SHA hashes. For each set of unique records it then goes and reads the first message
from disk and copies that into a new destination MBOX file.

The user has a choice (via the command-line) of which SHA hash value to use.

Recommendations
---------------

This program is provided entirely AS-IS and does not warrant that it will not do everything
right 100% of the time. Therefore it is recommended to:

- Setup a directory that has the data you want to process and at minimum symlink the source
  files into that directory.
- Run TBDedup outside the TB Profiles directory so it does not interfere with Thunderbird.
- At minimum keep Thunderbird in Offline Mode when testing and do not move files around in
  Thunderbird; though it would be better to close Thunderbird entirely so it is not running.
- Once a file set has been deduplicated then copy the resulting file back into where you
  want it inside of Thunderbird.

Installation
------------

This project is not associated with a PyPi release at this time. Therefore installation
will need to be done via the GitHub Project.

The easiest installation is likely just using `git`:

.. code-block:: shell

    $ git clone https://github.com/BenjamenMeyer/tbdedup
    $ cd tbdedup
    $ pip install .

Alternatively you may want to do the same in a Python VirtualEnv:

.. code-block:: shell

    $ git clone https://github.com/BenjamenMeyer/tbdedup
    $ python3 -m .venv
    $ source .venv/bin/activate
    (.venv) $ cd tbdedup
    (.venv) $ pip install .

This will put `tbdedup` into your environment based on your installation method.

.. note:: PyPi likely also can install directly from Git without having to check it out first.

Operations
----------

`tbdedup` can be run in a few different manners. It can be run run on each individual stage
or all together. The section below outline each method.

Running the Preplanner
----------------------

`tbdedup` provides the ability to search through a path to identify groups of files that should
be deduplicated together based the path within the Thunderbird Inbox. The basic idea is that
if something happens that the Inbox becomes recursively copied in on itself this would
identify the duplicated folders.

By default the preplanner will split on the `Inbox.sbd`:

.. code-block:: shell

    $ tb-dedup preplanner --location ~/.thunderbird/dm8a9v53.default/Mail/Local\ Folders/Inbox.sbd/

However, you can specify a different folder using the `--folder-pattern` parameter:

.. code-block:: shell

    $ tb-dedup preplanner --location ~/.thunderbird/dm8a9v53.default/Mail/Local\ Folders/Inbox.sbd/ --folder-pattern "Dedup/"

Running the Planner
-------------------

`tbdedup` provides a planner capability that will search a path and symlink files into a path
that can then be processed by the `dedup` functionality. This is useful for deduping multiple
locations in a Thunderbird Profile that have folders that can be pattern matched while ignoringG
other folders.

The planner will first build a listing of MBOX files. It will then create a timestamped folder
where it is run and symlink each MBOX file into that folder. Finally, it will record the
various data about the plan generation, the files found, and their associated symlink into
a JSON formatted file called `mapping.json` stored inside the folder next to the generated
symlinks. The `mapping.json` file allows for easy inspection of the plan, verification of
the plan, and the ability to repeat the plan if needed as the input parameters are recorded
in the map.

If you want to check all of the folders in one pass you can simply call it as follows:

.. code-block:: shell

    $ tb-dedup planner --location "~/.thunderbird/dm8a9v53.default/Mail/Local Folders"

This will produce a plan folder that will symlink every MBOX file within that path.
However, suppose you only want to get the files that have a common name of "personal/favors"
and it some how got copied multiple times across a variety of paths under the Local Folders.
Then you could run the following:

.. code-block:: shell

    $ tb-dedup planner --location "~/.thunderbird/dm8a9v53.default/Mail/Local Folders" --limit-pattern ".*\\personal\/favors$"


Running the Deduplication
-------------------------

`tbdedup` provides full support for Help documentation using the standard `-h` and `--help`
command-line parameters. Here is the basic usage:

.. code-block:: shell

    $ tb-dedup dedup --location <source location> --hash-storage <sqlite database storage location>

For example if you want it to search `~/myfiles` and store the data in `~/myfiles.hashes.sqlite`
you would run the following command:

.. code-block:: shell

    $ tb-dedup dedup --location ~/myfiles --hash-storage ~/myfiles.hashes.sqlite

`tbdedup` will output a timestamped file such as `20231123_091132_deduplicated.mbox` each time
it is run, allowing you to select which file to use as the final copy to restore to your
Thunderbird profile.

.. note:: I also found https://github.com/lenlo/mailcheck as a useful tool. It does offer dedup
   support; but it also seems to find issues with the length of the messages as stored by
   Thunderbird. Still it can provide a useful check that the output file is a valid MBOX file.

Running it all together
-----------------------

`tbdedup` provides the ability to run it all together. All the options available above are provided so they
can be appropriately applied. The functionality is basically the preplanner set to drive the planner,
which in turn drives the deduplicator.

.. note:: Running it all together may take a long time. Run-time will be based on the largest
   data set that is being processed, and the quantity of data sets being processed.

Example: 

.. code-block:: shell

    $ tb-dedup do --location ~/.thunderbird/dm8a9v53.default/Mail/Local\ Folders/Inbox.sbd/
