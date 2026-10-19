#!/usr/bin/env Rscript
# extract_nc.R
# Converts every .nc file in data/rainfall/nc/ into CSV file(s) in data/rainfall/data/.
# This script lives in data/rainfall/, so paths are resolved relative to its own location.
#
# Usage:  Rscript data/rainfall/extract_nc.R
# Needs:  install.packages("ncdf4")

suppressPackageStartupMessages(library(ncdf4))

# ---- locate directories relative to this script -----------------------------
args     <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
script_dir <- if (length(file_arg) > 0) {
  dirname(normalizePath(sub("^--file=", "", file_arg[1])))
} else {
  getwd()
}

nc_dir  <- file.path(script_dir, "nc")
out_dir <- file.path(script_dir, "data")

if (!dir.exists(nc_dir)) stop("Input directory not found: ", nc_dir)
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

# ---- helpers ----------------------------------------------------------------
# Convert a CF-style time axis ("days since 1900-01-01", etc.) to Date/POSIXct.
convert_time <- function(values, units) {
  m <- regmatches(units, regexec("^\\s*(\\w+)\\s+since\\s+(.+)$", units))[[1]]
  if (length(m) != 3) return(values)
  unit   <- tolower(m[2])
  origin <- tryCatch(as.POSIXct(m[3], tz = "UTC"), error = function(e) NA)
  if (is.na(origin)) return(values)
  secs <- switch(substr(unit, 1, 3),
                 sec = 1, min = 60, hou = 3600, day = 86400, NA)
  if (is.na(secs)) return(values)
  res <- origin + values * secs
  if (secs >= 86400) as.Date(res) else res
}

# ---- process each file ------------------------------------------------------
nc_files <- list.files(nc_dir, pattern = "\\.nc$", full.names = TRUE,
                       ignore.case = TRUE)
if (length(nc_files) == 0) stop("No .nc files found in ", nc_dir)

message("Found ", length(nc_files), " .nc file(s) in ", nc_dir)

for (f in nc_files) {
  base <- tools::file_path_sans_ext(basename(f))
  message("Processing: ", basename(f))

  res <- tryCatch({
    nc <- nc_open(f)
    on.exit(nc_close(nc), add = TRUE)

    # Keep real data variables (skip scalars and bounds variables)
    vars <- Filter(function(v) {
      v$ndims > 0 && !grepl("(bnds|bounds)$", v$name, ignore.case = TRUE)
    }, nc$var)

    if (length(vars) == 0) stop("no data variables found")

    # Group variables that share the same dimensions into one table
    sigs   <- vapply(vars, function(v) paste(vapply(v$dim, `[[`, "", "name"),
                                             collapse = "_"), "")
    groups <- split(vars, sigs)

    for (sig in names(groups)) {
      gv <- groups[[sig]]
      dims <- gv[[1]]$dim

      # Coordinate grid (first dimension varies fastest, matching R's array order)
      coord_list <- lapply(dims, function(d) {
        vals <- d$vals
        if (grepl("since", d$units, fixed = TRUE)) vals <- convert_time(vals, d$units)
        vals
      })
      names(coord_list) <- vapply(dims, `[[`, "", "name")
      df <- expand.grid(coord_list, KEEP.OUT.ATTRS = FALSE,
                        stringsAsFactors = FALSE)

      for (v in gv) {
        df[[v$name]] <- as.vector(ncvar_get(nc, v$name))
      }

      out_name <- if (length(groups) == 1) base else paste0(base, "_", sig)
      out_file <- file.path(out_dir, paste0(out_name, ".csv"))
      write.csv(df, out_file, row.names = FALSE)
      message("  -> ", out_file, " (", nrow(df), " rows)")
    }
    TRUE
  }, error = function(e) {
    message("  !! Failed on ", basename(f), ": ", conditionMessage(e))
    FALSE
  })
}

message("Done.")