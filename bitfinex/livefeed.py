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


import time
import datetime
import threading
import Queue

from pyalgotrade import bar
from pyalgotrade import barfeed
from pyalgotrade import dataseries
from pyalgotrade import logger
from pyalgotrade.utils import dt
from pyalgotrade import observer

import api


logger = logger.getLogger("bitfinex")


def utcnow():
    return dt.as_utc(datetime.datetime.utcnow())


class TradeBar(bar.Bar):
    __slots__ = ('__dateTime', '__tradeId', '__price', '__amount', '__type')

    last_datetime = None

    def __init__(self, bardict):
        trade_dt = datetime.datetime.fromtimestamp(bardict['timestamp'])
        if TradeBar.last_datetime is not None:
            if trade_dt <= TradeBar.last_datetime:
                trade_dt = (
                    TradeBar.last_datetime +
                    datetime.timedelta(seconds=0.01)
                )

        TradeBar.last_datetime = trade_dt
        self.__dateTime = trade_dt
        self.__tradeId = bardict['tid']
        self.__price = float(bardict['price'])
        self.__amount = float(bardict['amount'])
        self.__type = bardict['type']

    def __setstate__(self, state):
        (
            self.__dateTime,
            self.__tradeId,
            self.__price,
            self.__amount,
            self.__type
        ) = state

    def __getstate__(self):
        return (
            self.__dateTime,
            self.__tradeId,
            self.__price,
            self.__amount,
            self.__type
        )

    def setUseAdjustedValue(self, useAdjusted):
        if useAdjusted:
            raise Exception("Adjusted close is not available")

    def getTradeId(self):
        return self.__tradeId

    def getType(self):
        return self.__type

    def getFrequency(self):
        return bar.Frequency.TRADE

    def getDateTime(self):
        return self.__dateTime

    def getOpen(self, adjusted=False):
        return self.__price

    def getHigh(self, adjusted=False):
        return self.__price

    def getLow(self, adjusted=False):
        return self.__price

    def getClose(self, adjusted=False):
        return self.__price

    def getVolume(self):
        return self.__amount

    def getAdjClose(self):
        return None

    def getTypicalPrice(self):
        return self.__price

    def getPrice(self):
        return self.__price

    def getUseAdjValue(self):
        return False


class PollingThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.__stopped = False

    def __wait(self):
        nextCall = self.getNextCallDateTime()
        while not self.__stopped and utcnow() < nextCall:
            time.sleep(0.5)

    def stop(self):
        self.__stopped = True

    def stopped(self):
        return self.__stopped

    def run(self):
        logger.info("Thread started")
        while not self.__stopped:
            self.__wait()
            if not self.__stopped:
                try:
                    self.doCall()
                except Exception, e:
                    logger.critical("Unhandled exception", exc_info=e)
        logger.debug("Thread finished.")

    # Must return a non-naive datetime.
    def getNextCallDateTime(self):
        raise NotImplementedError()

    def doCall(self):
        raise NotImplementedError()


class TradesAPIThread(PollingThread):

    # Events
    ON_TRADE = 1
    ON_ORDER_BOOK_UPDATE = 2

    def __init__(self, queue, identifiers, apiCallDelay):
        PollingThread.__init__(self)

        self.__queue = queue
        self.__identifiers = identifiers
        self.__frequency = bar.Frequency.TRADE
        self.__apiCallDelay = apiCallDelay
        self.last_tid = 0
        self.last_orderbook_ts = 0

    def getNextCallDateTime(self):
        return utcnow() + self.__apiCallDelay

    def doCall(self):
        for identifier in self.__identifiers:
            try:
                trades = api.get_trades(identifier)
                trades.reverse()
                for barDict in trades:
                    bar = {}
                    trade = TradeBar(barDict)
                    bar[identifier] = trade
                    tid = trade.getTradeId()
                    if tid > self.last_tid:
                        self.last_tid = tid
                        self.__queue.put((
                            TradesAPIThread.ON_TRADE, bar
                        ))
                orders = api.get_orderbook(identifier)
                if len(orders['bids']) and len(orders['asks']):
                    best_ask = orders['asks'][0]
                    best_bid = orders['bids'][0]
                    last_update = max(
                        best_ask['timestamp'], best_bid['timestamp']
                    )
                    if last_update > self.last_orderbook_ts:
                        self.last_orderbook_ts = last_update
                        self.__queue.put((
                            TradesAPIThread.ON_ORDER_BOOK_UPDATE,
                            {
                                'bid': float(best_bid['price']),
                                'ask': float(best_ask['price'])
                            }
                        ))
            except api.BitfinexError, e:
                logger.error(e)


class LiveFeed(barfeed.BaseBarFeed):

    QUEUE_TIMEOUT = 0.01

    def __init__(
            self,
            identifiers,
            apiCallDelay=5,
            maxLen=dataseries.DEFAULT_MAX_LEN
    ):
        logger.info('Livefeed created')
        barfeed.BaseBarFeed.__init__(self, bar.Frequency.TRADE, maxLen)
        if not isinstance(identifiers, list):
            raise Exception("identifiers must be a list")

        self.__queue = Queue.Queue()
        self.__orderBookUpdateEvent = observer.Event()
        self.__thread = TradesAPIThread(
            self.__queue,
            identifiers,
            datetime.timedelta(seconds=apiCallDelay)
        )
        self.__bars = []
        for instrument in identifiers:
            self.registerInstrument(instrument)

    # observer.Subject interface
    def start(self):
        if self.__thread.is_alive():
            raise Exception("Already strated")
        self.__thread.start()

    def stop(self):
        self.__thread.stop()

    def join(self):
        if self.__thread.is_alive():
            self.__thread.join()

    def eof(self):
        return self.__thread.stopped()

    def peekDateTime(self):
        return None

    # barfeed.BaseBarFeed interface
    def getCurrentDateTime(self):
        return utcnow()

    def barsHaveAdjClose(self):
        return False

    def dispatch(self):
        ret = False
        if self.__dispatchImpl(None):
            ret = True
        if barfeed.BaseBarFeed.dispatch(self):
            ret = True
        return ret

    def __dispatchImpl(self, eventFilter):
        ret = False
        try:
            eventType, eventData = self.__queue.get(
                True, LiveFeed.QUEUE_TIMEOUT
            )
            if eventFilter is not None and eventType not in eventFilter:
                return False

            ret = True
            if eventType == TradesAPIThread.ON_TRADE:
                self.__onTrade(eventData)
            elif eventType == TradesAPIThread.ON_ORDER_BOOK_UPDATE:
                self.__orderBookUpdateEvent.emit(eventData)
            else:
                ret = False
                logger.error(
                    "Invalid event received to dispatch: %s - %s" % (
                        eventType, eventData
                    )
                )
        except Queue.Empty:
            pass
        return ret

    def __onTrade(self, barData):
        self.__bars.append(barData)

    def getNextBars(self):
        if len(self.__bars):
            return bar.Bars(self.__bars.pop(0))
        return None

    def getOrderBookUpdateEvent(self):
        return self.__orderBookUpdateEvent
