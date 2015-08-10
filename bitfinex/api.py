# PyAlgoTrade BitFinex module
#
# Copyright 2011-2015 Gabriel Martin Becedillas Ruiz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Modified from PyAlgoTrade Bitstamp and Xignite modules

"""
.. moduleauthor:: Mikko Gozalo <mikgozalo@gmail.com>
"""


import urllib2
import json


class BitfinexError(Exception):
    def __init__(self, message, response):
        Exception.__init__(self, message)


def json_http_request(url):
    f = urllib2.urlopen(url)
    response = f.read()
    return json.loads(response)


def get_trades(currency_pair):
    url = "https://api.bitfinex.com/v1/trades/{}".format(currency_pair)
    try:
        ret = json_http_request(url)
    except:
        raise BitfinexError('Problem fetching trades')
    return ret


def get_orderbook(currency_pair):
    url = "https://api.bitfinex.com/v1/book/{}".format(currency_pair)
    try:
        ret = json_http_request(url)
    except:
        raise BitfinexError('Problem fetching trades')
    return ret
