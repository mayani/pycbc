# Copyright (C) 2020  Collin Capano, Alex Nitz
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Provides functions and utilities for generating waveforms mode-by-mode.
"""

from string import Formatter
import lal

from pycbc import libutils, pnutils
from pycbc.types import (TimeSeries, FrequencySeries)
from .waveform import (props, _check_lal_pars, check_args)
from . import parameters

lalsimulation = libutils.import_optional('lalsimulation')

def _formatdocstr(docstr):
    """Utility for formatting docstrings with parameter information.
    """
    return docstr.format(
        **{_p[1]: getattr(parameters, _p[1]).docstr(
            prefix="    ", include_label=False).lstrip(' ')
           for _p in Formatter().parse(docstr) if _p[1] is not None
           })


def _formatdocstrlist(docstr, paramlist, skip_params=None):
    """Utility for formatting docstrings with parameter information.
    """
    if skip_params is None:
        skip_params = []
    pl = '\n'.join([_p.docstr(prefix="    ", include_label=False)
                    for _p in paramlist if _p not in skip_params]).lstrip(' ')
    return docstr.format(params=pl)


def sum_modes(hlms, inclination, phi):
    """Applies spherical harmonics and sums modes to produce a plus and cross
    polarization.

    Parameters
    ----------
    hlms : dict
        Dictionary of ``(l, m)`` -> complex ``hlm``. The ``hlm`` may be a
        complex number or array, or complex ``TimeSeries``. All modes in the
        dictionary will be summed.
    inclination : float
        The inclination to use.
    phi : float
        The phase to use.

    Returns
    -------
    complex float or array
        The plus and cross polarization as a complex number. The real part
        gives the plus, the negative imaginary part the cross.
    """
    out = None
    for mode in hlms:
        l, m = mode
        hlm = hlms[l, m]
        ylm = lal.SpinWeightedSphericalHarmonic(inclination, phi, -2, l, m)
        if out is None:
            out = ylm * hlm
        else:
            out += ylm * hlm
    return out


def default_modes(approximant):
    """Returns the default modes for the given approximant.
    """
    # FIXME: this should be replaced to a call to a lalsimulation function,
    # whenever that's added
    if approximant in ['IMRPhenomXPHM', 'IMRPhenomXHM']:
        # according to arXiv:2004.06503
        ma = [(2, 2), (2, 1), (3, 3), (3, 2), (4, 4)]
        # add the -m modes
        ma += [(l, -m) for l, m in ma]
    elif approximant in ['IMRPhenomPv3HM', 'IMRPhenomHM']:
        # according to arXiv:1911.06050
        ma = [(2, 2), (2, 1), (3, 3), (3, 2), (4, 4), (4, 3)]
        # add the -m modes
        ma += [(l, -m) for l, m in ma]
    elif approximant.startswith('NRSur7dq4'):
        # according to arXiv:1905.09300
        ma = [(l, m) for l in [2, 3, 4] for m in range(-l, l+1)]
    elif approximant.startswith('NRHybSur3dq8'):
        # according to arXiv:1812.07865
        ma = [(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2),
              (3, 3), (4, 2), (4, 3), (4, 4), (5, 5)]
    else:
        raise ValueError("I don't know what the default modes are for "
                         "approximant {}, sorry!".format(approximant))
    return ma


def get_glm(l, m, theta):
    r"""The maginitude of the :math:`{}_{-2}Y_{\ell m}`.

    The spin-weighted spherical harmonics can be written as
    :math:`{}_{-2}Y_{\ell m}(\theta, \phi) = g_{\ell m}(\theta)e^{i m \phi}`.
    This returns the `g_{\ell m}(\theta)` part. Note that this is real.

    Parameters
    ----------
    l : int
        The :math:`\ell` index of the spherical harmonic.
    m : int
        The :math:`m` index of the spherical harmonic.
    theta : float
        The polar angle (in radians).

    Returns
    -------
    float :
        The amplitude of the harmonic at the given polar angle.
    """
    return lal.SpinWeightedSphericalHarmonic(theta, 0., -2, l, m).real


def get_nrsur_modes(**params):
    """Generates NRSurrogate waveform mode-by-mode.

    All waveform parameters should be provided as keyword arguments.
    Recognized parameters are listed below. Unrecognized arguments are ignored.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    approximant : str
        The approximant to generate. Must be one of the ``NRSur*`` models.
    {delta_t}
    {mass1}
    {mass2}
    {spin1x}
    {spin1y}
    {spin1z}
    {spin2x}
    {spin2y}
    {spin2z}
    {f_lower}
    {f_ref}
    {distance}
    {mode_array}

    Returns
    -------
    dict :
        Dictionary of ``(l, m)`` -> ``(h_+, -h_x)`` ``TimeSeries``.
    """
    laldict = _check_lal_pars(params)
    ret = lalsimulation.SimInspiralPrecessingNRSurModes(
        params['delta_t'],
        params['mass1']*lal.MSUN_SI,
        params['mass2']*lal.MSUN_SI,
        params['spin1x'], params['spin1y'], params['spin1z'],
        params['spin2x'], params['spin2y'], params['spin2z'],
        params['f_lower'], params['f_ref'],
        params['distance']*1e6*lal.PC_SI, laldict,
        getattr(lalsimulation, params['approximant'])
    )
    hlms = {}
    while ret:
        hlm = TimeSeries(ret.mode.data.data, delta_t=ret.mode.deltaT,
                         epoch=ret.mode.epoch)
        hlms[ret.l, ret.m] = (hlm.real(), hlm.imag())
        ret = ret.next
    return hlms

def get_nrhybsur_modes(**params):
    """Generates NRHybSur3dq8 waveform mode-by-mode.

    All waveform parameters should be provided as keyword arguments.
    Recognized parameters are listed below. Unrecognized arguments are ignored.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    approximant : str
        The approximant to generate. Must be one of the ``NRHyb*`` models.
    {delta_t}
    {mass1}
    {mass2}
    {spin1z}
    {spin2z}
    {f_lower}
    {f_ref}
    {distance}
    {mode_array}

    Returns
    -------
    dict :
        Dictionary of ``(l, m)`` -> ``(h_+, -h_x)`` ``TimeSeries``.
    """
    laldict = _check_lal_pars(params)
    ret = lalsimulation.SimIMRNRHybSur3dq8Modes(
        params['delta_t'],
        params['mass1']*lal.MSUN_SI,
        params['mass2']*lal.MSUN_SI,
        params['spin1z'],
        params['spin2z'],
        params['f_lower'], params['f_ref'],
        params['distance']*1e6*lal.PC_SI, laldict
    )
    hlms = {}
    while ret:
        hlm = TimeSeries(ret.mode.data.data, delta_t=ret.mode.deltaT,
                         epoch=ret.mode.epoch)
        hlms[ret.l, ret.m] = (hlm.real(), hlm.imag())
        ret = ret.next
    return hlms


get_nrsur_modes.__doc__ = _formatdocstr(get_nrsur_modes.__doc__)
get_nrhybsur_modes.__doc__ = _formatdocstr(get_nrhybsur_modes.__doc__)

def get_lalsimulation_approximant(approximant):
    import lalsimulation as ls
    return {
        'EOBNRv2': ls.EOBNRv2,
        'EOBNRv2HM': ls.EOBNRv2HM,
        'IMRPhenomTPHM': ls.IMRPhenomTPHM,
        'NRSur7dq2': ls.NRSur7dq2,
        'NRSur7dq4': ls.NRSur7dq4,
        'NRHybSur3dq8': ls.NRHybSur3dq8,
        'pSEOBNRv4HM_PA': ls.pSEOBNRv4HM_PA,
        'SEOBNRv4HM_PA': ls.SEOBNRv4HM_PA,
        'SEOBNRv4P': ls.SEOBNRv4P,
        'SEOBNRv4PHM': ls.SEOBNRv4PHM,
        'SpinTaylorT1': ls.SpinTaylorT1,
        'SpinTaylorT4': ls.SpinTaylorT4,
        'SpinTaylorT5': ls.SpinTaylorT5,
        'TaylorT1': ls.TaylorT1,
        'TaylorT2': ls.TaylorT2,
        'TaylorT3': ls.TaylorT3,
        'TaylorT4': ls.TaylorT4,
        }[approximant]

def get_lalsimulation_modes(**params):
    """Generates approximant waveform mode-by-mode.

    All waveform parameters should be provided as keyword arguments.
    Recognized parameters are listed below. Unrecognized arguments are ignored.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to substitute
        for keyword arguments. A common example would be a row in an xml table.
    approximant : str
        The approximant to generate. Must be available in ``lalsimulation``.
    {delta_t}
    {mass1}
    {mass2}
    {spin1x}
    {spin1y}
    {spin1z}
    {spin2x}
    {spin2y}
    {spin2z}
    {f_lower}
    {f_ref}
    {distance}
    {mode_array}
    {ell_max}
    {approximant}

    Returns
    -------
    dict :
        Dictionary of ``(l, m)`` -> ``(h_+, -h_x)`` ``TimeSeries``.
    """
    ell_max = 5
    if 'ell_max' in params:
        ell_max = params['ell_max']
    laldict = _check_lal_pars(params)
    ret = lalsimulation.SimInspiralChooseTDModes(
        params['coa_phase'],
        params['delta_t'],
        params['mass1']*lal.MSUN_SI,
        params['mass2']*lal.MSUN_SI,
        params['spin1x'],
        params['spin1y'],
        params['spin1z'],
        params['spin2x'],
        params['spin2y'],
        params['spin2z'],
        params['f_lower'], params['f_ref'],
        params['distance']*1e6*lal.PC_SI, laldict,
        ell_max,
        get_lalsimulation_approximant(params['approximant'])
    )
    hlms = {}
    while ret:
        hlm = TimeSeries(ret.mode.data.data, delta_t=ret.mode.deltaT,
                         epoch=ret.mode.epoch)
        hlms[(ret.l, ret.m)] = (hlm.real(), hlm.imag())
        ret = ret.next
    return hlms

def get_imrphenomxh_modes(**params):
    """Generates ``IMRPhenomXHM`` waveforms mode-by-mode. """
    approx = params['approximant']
    if not approx.startswith('IMRPhenomX'):
        raise ValueError("unsupported approximant")
    mode_array = params.pop('mode_array', None)
    if mode_array is None:
        mode_array = default_modes(approx)
    if 'f_final' not in params:
        # setting to 0 will default to ringdown frequency
        params['f_final'] = 0.
    hlms = {}
    for (l, m) in mode_array:
        params['mode_array'] = [(l, m)]
        laldict = _check_lal_pars(params)
        hlm = lalsimulation.SimIMRPhenomXHMGenerateFDOneMode(
            float(pnutils.solar_mass_to_kg(params['mass1'])),
            float(pnutils.solar_mass_to_kg(params['mass2'])),
            float(params['spin1z']),
            float(params['spin2z']), l, m,
            pnutils.megaparsecs_to_meters(float(params['distance'])),
            params['f_lower'], params['f_final'], params['delta_f'],
            params['coa_phase'], params['f_ref'],
            laldict)
        hlm = FrequencySeries(hlm.data.data, delta_f=hlm.deltaF,
                              epoch=hlm.epoch)
        # Plus, cross strains without Y_lm.
        # (-1)**(l) factor ALREADY included in FDOneMode
        hplm = 0.5 * hlm  # Plus strain
        hclm = 0.5j * hlm  # Cross strain
        if m > 0:
            hclm *= -1
        hlms[l, m] = (hplm, hclm)
    return hlms


_mode_waveform_td = {'EOBNRv2': get_lalsimulation_modes,
                     'EOBNRv2HM': get_lalsimulation_modes,
                     'IMRPhenomTPHM': get_lalsimulation_modes,
                     'NRSur7dq2': get_lalsimulation_modes,
                     'NRSur7dq4': get_nrsur_modes,
                     'NRHybSur3dq8': get_nrhybsur_modes,
                     'pSEOBNRv4HM_PA': get_lalsimulation_modes,
                     'SEOBNRv4HM_PA': get_lalsimulation_modes,
                     'SEOBNRv4P': get_lalsimulation_modes,
                     'SEOBNRv4PHM': get_lalsimulation_modes,
                     'SpinTaylorT1': get_lalsimulation_modes,
                     'SpinTaylorT4': get_lalsimulation_modes,
                     'SpinTaylorT5': get_lalsimulation_modes,
                     'TaylorT1': get_lalsimulation_modes,
                     'TaylorT2': get_lalsimulation_modes,
                     'TaylorT3': get_lalsimulation_modes,
                     'TaylorT4': get_lalsimulation_modes,
                     }
_mode_waveform_fd = {'IMRPhenomXHM': get_imrphenomxh_modes,
                     }
# 'IMRPhenomXPHM':get_imrphenomhm_modes needs to be implemented
# LAL function do not split strain mode by mode

def fd_waveform_mode_approximants():
    """Frequency domain approximants that will return separate modes."""
    return sorted(_mode_waveform_fd.keys())


def td_waveform_mode_approximants():
    """Time domain approximants that will return separate modes."""
    return sorted(_mode_waveform_td.keys())


def get_fd_waveform_modes(template=None, **kwargs):
    r"""Generates frequency domain waveforms, but does not sum over the modes.

    The returned values are the frequency-domain equivalents of the real and
    imaginary parts of the complex :math:`\mathfrak{{h}}_{{\ell m}}(t)` time
    series. In other words, the returned values are equivalent to the Fourier
    Transform of the two time series returned by
    :py:func:`get_td_waveform_modes`; see that function for more details.

    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to subsitute
        for keyword arguments.
    {params}

    Returns
    -------
    ulm : dict
        Dictionary of mode tuples -> fourier transform of the real part of the
        hlm time series, as a :py:class:`pycbc.types.FrequencySeries`.
    vlm : dict
        Dictionary of mode tuples -> fourier transform of the imaginary part of
        the hlm time series, as a :py:class:`pycbc.types.FrequencySeries`.
    """
    params = props(template, **kwargs)
    required = parameters.fd_required
    check_args(params, required)
    apprx = params['approximant']
    if apprx not in _mode_waveform_fd:
        raise ValueError("I don't support approximant {}, sorry"
                         .format(apprx))
    return _mode_waveform_fd[apprx](**params)


get_fd_waveform_modes.__doc__ = _formatdocstrlist(
    get_fd_waveform_modes.__doc__, parameters.fd_waveform_params,
    skip_params=['inclination', 'coa_phase'])


def get_td_waveform_modes(template=None, **kwargs):
    r"""Generates time domain waveforms, but does not sum over the modes.

    The returned values are the real and imaginary parts of the complex
    :math:`\mathfrak{{h}}_{{\ell m}}(t)`. These are defined such that the plus
    and cross polarizations :math:`h_{{+,\times}}` are:

    .. math::

       h_{{+,\times}}(\theta, \phi; t) = (\Re, -\Im) \sum_{{\ell m}}
        {{}}_{{-2}}Y_{{\ell m}}(\theta, \phi) \mathfrak{{h}}_{{\ell m}}(t).


    Parameters
    ----------
    template: object
        An object that has attached properties. This can be used to subsitute
        for keyword arguments.
    {params}

    Returns
    -------
    ulm : dict
        Dictionary of mode tuples -> real part of the hlm, as a
        :py:class:`pycbc.types.TimeSeries`.
    vlm : dict
        Dictionary of mode tuples -> imaginary part of the hlm, as a
        :py:class:`pycbc.types.TimeSeries`.
    """
    params = props(template, **kwargs)
    required = parameters.td_required
    check_args(params, required)
    apprx = params['approximant']
    if apprx not in _mode_waveform_td:
        raise ValueError("I don't support approximant {}, sorry"
                         .format(apprx))
    return _mode_waveform_td[apprx](**params)


get_td_waveform_modes.__doc__ = _formatdocstrlist(
    get_td_waveform_modes.__doc__, parameters.td_waveform_params,
    skip_params=['inclination', 'coa_phase'])
