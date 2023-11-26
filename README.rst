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
