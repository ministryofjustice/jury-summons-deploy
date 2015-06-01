Config and Deploy repo for [jury-summons](https://github.com/ministryofjustice/jury-summons)
============================================================================================

The files are encrypted using [BlackBox](https://github.com/StackExchange/blackbox) which needs to be installed globally on your computer.


How to install BlackBox
=======================

The easiest way is to pull the repository and add the `bin` folder in it to your PATH.

```
cd /usr/local/opt
git clone git@github.com:StackExchange/blackbox.git
echo 'export PATH="/usr/local/opt/blackbox/bin/:$PATH"' >> $HOME/.bash_profile
source $HOME/.bash_profile
```

You will know have access to the blackbox_* commands.


Overview
========

Secret files are stored in this repo using the .gpg extension (e.g. *myfile.gpg*).

When you decrypt a file it gets saved in an additional file without the the gpg extension (e.g. *myfile*).

Unencrypted files are always gitignored so that cannot be pushed by mistake.

Blackbox manages everything for you so you don't need to remember anything in particular (it updates the gitignore file as well when adding new files to be encrypted).


How to use it
=============

If you don't have permissions, you need to ask one of the admins to add you as user. Ask one of these:

```
cat keyrings/live/blackbox-admins.txt
```

Then pull and follow below.

To decrypt just run:
```
blackbox_edit_start <myfile>
```

This will decrypt `myfile`.

After done with it, you can either:

1. IF you have changed the file => encrypt the new version and push it
```
blackbox_edit_end <myfile>
git commit -a -m <your message>
git push origin masater
```

2. IF you haven't changed the file => delete the decrypted file from your local machine, just to be safe:
```
blackbox_shred_all_files
```


How to manage users
===================

Add a new user
--------------

You need to have the pub key of the user in your gpg keychain.

You can get this by asking them directly or by using [keybase](https://keybase.io) (recommended).

Then run:

```
blackbox_addadmin newuser@example.com
# commit the changes by copying and pasting the command included in the output of the line above (e.g. git commit -m ...)
blackbox_update_all_files
git push origin master
```

After this, the new user will be able to decrypt and encrypt files.

Read more [on blackbox](https://github.com/StackExchange/blackbox#how-to-indoctrinate-a-new-user-into-the-system).

Remove a user
-------------

Read [on blackbox](https://github.com/StackExchange/blackbox#how-to-remove-a-user-from-the-system) or below for a quick setup.

```
blackbox_removeadmin olduser@example.com
blackbox_update_all_files
git commit -a -m <your message>
git push origin master
```

That's it!

**WARNING**: the user will still be able to access the old version so in theory we should really change the secrets every time we remove a user.

If you want to clean after yourself, you should also delete the pub key of the removed user from the repo.

```
gpg --homedir=keyrings/live --list-keys
gpg --homedir=keyrings/live --delete-key olduser@example.com
git commit -m'Cleaned olduser@example.com from keyring'  keyrings/live/*
```
