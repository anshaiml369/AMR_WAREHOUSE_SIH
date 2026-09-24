# WAREHOUSE 70% STABLE BASELINE

This checkpoint represents the known-good WAREHOUSE state before subsequent modifications.

## Recovery branch

warehouse-70pct-stable

## Recovery tag

warehouse-v70-stable

## Recovery command

git switch warehouse-70pct-stable

## If the current branch contains failed experimental changes

First preserve any desired work separately.

Then:

git switch warehouse-70pct-stable

If the working tree must exactly match the checkpoint:

git reset --hard warehouse-70pct-stable

DO NOT run the reset command until any valuable uncommitted work has been preserved.

## Important

Never modify the warehouse-70pct-stable branch for future development.

Future development must happen on a new branch created from this checkpoint.
