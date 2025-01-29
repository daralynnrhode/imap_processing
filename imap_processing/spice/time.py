"""Time conversion functions that rely on SPICE."""

import typing
from collections.abc import Collection, Iterable
from typing import Union

import numpy as np
import numpy.typing as npt
import spiceypy as spice

from imap_processing.spice import IMAP_SC_ID
from imap_processing.spice.kernels import ensure_spice

TICK_DURATION = 2e-5  # 20 microseconds as defined in imap_sclk_0000.tsc

# Hard code the J2000 epoch. This allows for CDF epoch to be converted without
# use of SPICE though it should be noted that this results in a 5-second error
# due to the occurrence of 5 leap-seconds since the J2000 epoch.
# TODO: Implement a function for converting CDF epoch to UTC correctly.
#     see github ticket #1208
# The UTC string was generated by:
# >>> spiceypy.et2utc(spiceypy.unitim(0, "TT", "ET"), "ISOC", 9)
TTJ2000_EPOCH = np.datetime64("2000-01-01T11:58:55.816", "ns")


def met_to_sclkticks(met: npt.ArrayLike) -> npt.NDArray[float]:
    """
    Convert Mission Elapsed Time (MET) to floating point spacecraft clock ticks.

    Parameters
    ----------
    met : float, numpy.ndarray
        Number of seconds since epoch according to the spacecraft clock.

    Returns
    -------
    numpy.ndarray[float]
        The mission elapsed time converted to nanoseconds since the J2000 epoch.
    """
    return np.asarray(met, dtype=float) / TICK_DURATION


def met_to_ttj2000ns(
    met: npt.ArrayLike,
) -> npt.NDArray[np.int64]:
    """
    Convert mission elapsed time (MET) to terrestrial time nanoseconds since J2000.

    Parameters
    ----------
    met : float, numpy.ndarray
        Number of seconds since epoch according to the spacecraft clock.

    Returns
    -------
    numpy.ndarray[numpy.int64]
        The mission elapsed time converted to nanoseconds since the J2000 epoch
        in the terrestrial time (TT) timescale.

    Notes
    -----
    There are two options when using SPICE to convert from SCLK time (MET) to
    J2000. The conversion can be done on SCLK strings as input or using double
    precision continuous spacecraft clock "ticks". The latter is more accurate
    as it will correctly convert fractional clock ticks to nanoseconds. Since
    some IMAP instruments contain clocks with higher precision than 1 SCLK
    "tick" which is defined to be 20 microseconds, according to the sclk kernel,
    it is preferable to use the higher accuracy method.
    """
    sclk_ticks = met_to_sclkticks(met)
    return np.asarray(sct_to_ttj2000s(sclk_ticks) * 1e9, dtype=np.int64)


@typing.no_type_check
@ensure_spice
def ttj2000ns_to_et(tt_ns: npt.ArrayLike) -> npt.NDArray[float]:
    """
    Convert TT J2000 epoch nanoseconds to TDB J2000 epoch seconds.

    The common CDF coordinate `epoch` stores terrestrial time (TT) J2000
    nanoseconds. SPICE requires Barycentric Dynamical Time (TDB, aka ET) J2000
    floating point seconds for most geometry related functions. This is a common
    function to do that conversion.

    Parameters
    ----------
    tt_ns : float, numpy.ndarray
        Number of nanoseconds since the J2000 epoch in the TT timescale.

    Returns
    -------
    numpy.ndarray[float]
        Number of seconds since the J2000 epoch in the TDB timescale.
    """
    tt_seconds = np.asarray(tt_ns, dtype=np.float64) / 1e9
    vectorized_unitim = np.vectorize(
        spice.unitim, [float], excluded=["insys", "outsys"]
    )
    return vectorized_unitim(tt_seconds, "TT", "ET")


@typing.no_type_check
@ensure_spice(time_kernels_only=True)
def met_to_utc(met: npt.ArrayLike, precision: int = 9) -> npt.NDArray[str]:
    """
    Convert mission elapsed time (MET) to UTC.

    Parameters
    ----------
    met : float, numpy.ndarray
        Number of seconds since epoch according to the spacecraft clock.
    precision : int
        The number of digits of precision to which fractional seconds
        are to be computed.

    Returns
    -------
    numpy.ndarray[str]
        The mission elapsed time converted to UTC string. The UTC string(s)
        returned will be of the form '1987-04-12T16:31:12.814' with the
        fractional seconds precision as specified by the precision keyword.
    """
    sclk_ticks = met_to_sclkticks(met)
    et = _sct2e_wrapper(sclk_ticks)
    return spice.et2utc(et, "ISOC", prec=precision)


def met_to_datetime64(
    met: npt.ArrayLike,
) -> Union[np.datetime64, npt.NDArray[np.datetime64]]:
    """
    Convert mission elapsed time (MET) to datetime.datetime.

    Parameters
    ----------
    met : float, numpy.ndarray
        Number of seconds since epoch according to the spacecraft clock.

    Returns
    -------
    numpy.ndarray[str]
        The mission elapsed time converted to UTC string.
    """
    if isinstance(met, typing.Iterable):
        return np.asarray([np.datetime64(utc) for utc in met_to_utc(met)])
    return np.datetime64(met_to_utc(met))


@typing.no_type_check
@ensure_spice
def _sct2e_wrapper(
    sclk_ticks: Union[float, Collection[float]],
) -> Union[float, np.ndarray]:
    """
    Convert encoded spacecraft clock "ticks" to ephemeris time.

    Decorated wrapper for spiceypy.sct2e that vectorizes the function in addition
    to wrapping with the @ensure_spice automatic kernel furnishing functionality.
    https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/sct2e_c.html

    Parameters
    ----------
    sclk_ticks : Union[float, Collection[float]]
        Input sclk ticks value(s) to be converted to ephemeris time.

    Returns
    -------
    ephemeris_time: np.ndarray
        Ephemeris time, seconds past J2000.
    """
    if isinstance(sclk_ticks, Collection):
        return np.array([spice.sct2e(IMAP_SC_ID, s) for s in sclk_ticks])
    else:
        return spice.sct2e(IMAP_SC_ID, sclk_ticks)


@typing.no_type_check
@ensure_spice
def sct_to_ttj2000s(
    sclk_ticks: Union[float, Collection[float]],
) -> Union[float, np.ndarray]:
    """
    Convert encoded spacecraft clock "ticks" to terrestrial time (TT).

    Decorated wrapper for chained spiceypy functions `unitim(sct2e(), "ET", "TT")`
    that vectorizes the functions in addition to wrapping with the @ensure_spice
    automatic kernel furnishing functionality.
    https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/sct2e_c.html
    https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/unitim_c.html

    Parameters
    ----------
    sclk_ticks : Union[float, Collection[float]]
        Input sclk ticks value(s) to be converted to ephemeris time.

    Returns
    -------
    terrestrial_time: np.ndarray[float]
        Terrestrial time, seconds past J2000.
    """
    if isinstance(sclk_ticks, Collection):
        return np.array(
            [spice.unitim(spice.sct2e(IMAP_SC_ID, s), "ET", "TT") for s in sclk_ticks]
        )
    else:
        return spice.unitim(spice.sct2e(IMAP_SC_ID, sclk_ticks), "ET", "TT")


@typing.no_type_check
@ensure_spice
def str_to_et(
    time_str: Union[str, Iterable[str]],
) -> Union[float, np.ndarray]:
    """
    Convert string to ephemeris time.

    Decorated wrapper for spiceypy.str2et that vectorizes the function in addition
    to wrapping with the @ensure_spice automatic kernel furnishing functionality.
    https://spiceypy.readthedocs.io/en/main/documentation.html#spiceypy.spiceypy.str2et

    Parameters
    ----------
    time_str : str or Iterable[str]
        Input string(s) to be converted to ephemeris time.

    Returns
    -------
    ephemeris_time: np.ndarray
        Ephemeris time, seconds past J2000.
    """
    if isinstance(time_str, str):
        return spice.str2et(time_str)
    else:
        return np.array([spice.str2et(t) for t in time_str])


@typing.no_type_check
@ensure_spice
def et_to_utc(
    et: Union[float, Iterable[float]],
    format_str: str = "ISOC",
    precision: int = 3,
    utclen: int = 24,
) -> Union[str, np.ndarray]:
    """
    Convert ephemeris time to UTC.

    Decorated wrapper for spiceypy.et2utc that vectorizes the function in addition
    to wrapping with the @ensure_spice automatic kernel furnishing functionality.
    https://spiceypy.readthedocs.io/en/main/documentation.html#spiceypy.spiceypy.et2utc

    Parameters
    ----------
    et : float or Iterable[float]
        Input ephemeris time(s) to be converted to UTC.
    format_str : str
        Format of the output time string. Default is "ISOC". All options:
        "C" Calendar format, UTC.
        "D" Day-of-Year format, UTC.
        "J" Julian Date format, UTC.
        "ISOC" ISO Calendar format, UTC.
        "ISOD" ISO Day-of-Year format, UTC.
    precision : int
        Digits of precision in fractional seconds or days. Default is 3.
    utclen : int
        The length of the output string. Default is 24 (to accommodate the
        "YYYY-MM-DDT00:00:00.000" format + 1). From the NAIF docs: if the output string
        is expected to have `x` characters, utclen` must be x + 1.

    Returns
    -------
    utc_time : str or np.ndarray
        UTC time(s).
    """
    return spice.et2utc(et, format_str, precision, utclen)
