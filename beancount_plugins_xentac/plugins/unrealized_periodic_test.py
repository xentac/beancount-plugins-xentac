__author__ = "Martin Blais <blais@furius.ca>"

import unittest
import re

from beancount_plugins_xentac.plugins import unrealized_periodic
from beancount.core.number import D
from beancount.core.number import ZERO
from beancount.core import data
from beancount.core import inventory
from beancount.parser import options
from beancount.ops import validation
from beancount.ops import summarize
from beancount import loader


def get_entries_with_narration(entries, regexp):
    """Return the entries whose narration matches the regexp.

    Args:
      entries: A list of directives.
      regexp: A regular expression string, to be matched against the
        narration field of transactions.
    Returns:
      A list of directives.
    """
    return [entry
            for entry in entries
            if (isinstance(entry, data.Transaction) and
                re.search(regexp, entry.narration))]


class TestUnrealized(unittest.TestCase):

    def test_empty_entries(self):
        entries, _ = unrealized_periodic.add_unrealized_gains([], options.OPTIONS_DEFAULTS.copy())
        self.assertEqual([], entries)

    @loader.load_doc()
    def test_nothing_held_at_cost(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Assets:Account2
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1

        2014-01-16 *
          Income:Misc           -1000 EUR
          Assets:Account2

        2014-02-01 price EUR  1.34 USD
        """
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        self.assertEqual(new_entries, entries)
        self.assertEqual([],
                         unrealized_periodic.get_unrealized_entries(new_entries))

    @loader.load_doc()
    def test_normal_case(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Assets:Account2
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-16 *
          Income:Misc           -600 USD
          Assets:Account1       5 HOUSE {120 USD}

        2014-01-17 *
          Income:Misc           -1000 EUR
          Assets:Account2       5 MANSION {200 EUR}

        2014-01-18 * "Bought through a price conversion, not held at cost."
          Income:Misc           -1500 EUR
          Assets:Account2       5 HOTEL @ 300 EUR

        2014-02-01 price HOUSE    130 USD
        2014-02-01 price MANSION  180 EUR
        2014-02-01 price HOTEL    330 USD
        """
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)

        self.assertEqual(2, len(unrealized_periodic.get_unrealized_entries(new_entries)))

        house = get_entries_with_narration(new_entries, "units of HOUSE")[0]
        self.assertEqual(2, len(house.postings))
        self.assertEqual(D('350'), house.postings[0].units.number)
        self.assertEqual('Assets:Account1', house.postings[0].account)
        self.assertEqual('Income:Account1', house.postings[1].account)

        mansion = get_entries_with_narration(new_entries, "units of MANSION")[0]
        self.assertEqual(2, len(mansion.postings))
        self.assertEqual(D('-100'), mansion.postings[0].units.number)

    @loader.load_doc()
    def test_no_price(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        """
        # Well... if there is a cost, there is at least one price, derived from
        # the cost entry. This won't generate an unrealized transaction because there is no difference.
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(0, len(unreal_entries))

    @loader.load_doc()
    def test_immediate_profit(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD} @ 120 USD

        2014-01-15 price HOUSE  120 USD
        """
        # Well... if there is a cost, there is at least one price, derived from
        # the cost entry.
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(1, len(unreal_entries))
        self.assertEqual(D('200'),
                         unreal_entries[0].postings[0].units.number)

    @loader.load_doc()
    def test_three_months(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        2014-01-20 price HOUSE  120 USD
        2014-02-25 price HOUSE  140 USD
        2014-03-25 price HOUSE  100 USD
        """
        # There should be three unrealized transactions
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(3, len(unreal_entries))
        for target, actual in zip(
                [(None, D('200')), (D('-200'), D('400')), (D('-400'), ZERO)],
                unreal_entries):
            if target[0] is not None:
                self.assertEqual(target[0], actual.postings[2].units.number)
            self.assertEqual(target[1], actual.postings[0].units.number)

    @loader.load_doc()
    def test_relative_gain_loss(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        2014-01-20 price HOUSE  150 USD ; Actual gain/Relative gain
        2014-02-25 price HOUSE  140 USD ; Actual gain/Relative loss
        2014-03-25 price HOUSE  50 USD  ; Actual loss/Relative loss
        2014-04-25 price HOUSE  70 USD  ; Actual loss/Relative gain
        """
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(4, len(unreal_entries))
        for target, actual in zip(
                ['gain', 'loss', 'loss', 'gain'],
                unreal_entries):
            self.assertTrue(actual.narration.startswith('Unrealized ' + target))

    @loader.load_doc()
    def test_change_commodity_subaccount(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc
        2014-01-01 open Income:Pnl

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        2014-01-20 price HOUSE  125 USD
        2014-02-05 price HOUSE  150 USD

        2014-02-15 *
          Assets:Account1      -10 HOUSE {100 USD}
          Assets:Account1       30 CAR {50 USD}
          Income:Pnl           -500 USD
        2014-02-15 price CAR  50 USD
        2014-02-20 price CAR  100 USD
        """
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map, subaccount='Unrealized')
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(3, len(unreal_entries))
        self.assertEqual(2, len(unreal_entries[-2].postings))  # The second to last transaction zeroed the account
        self.assertEqual(2, len(unreal_entries[-1].postings))  # The last transaction added the new unrealized gain
        summary = summarize.balance_by_account(unreal_entries)
        self.assertEqual(summary[0]['Assets:Account1:Unrealized'], inventory.Inventory.from_string("1500 USD"))

    @loader.load_doc()
    def test_all_unrealized_realized(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Assets:Cash
        2014-01-01 open Income:Misc
        2014-01-01 open Income:PnL

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        2014-01-20 price HOUSE  120 USD

        2014-02-10 *
          Assets:Cash           3000 USD
          Assets:Account1       -10 HOUSE {100 USD}
          Income:PnL            -2000 USD
        """
        # The goal is to have two transactions, one that registers the unrealized
        # profit and the other that negates it because there has been real profit
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(2, len(unreal_entries))
        for target, actual in zip(
                [(None, D('200')), (None, D('-200'))],
                unreal_entries):
            if target[0] is not None:
                self.assertEqual(target[0], actual.postings[2].units.number)
            self.assertEqual(target[1], actual.postings[0].units.number)

    @loader.load_doc()
    def test_clear_then_new(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Assets:Cash
        2014-01-01 open Income:Misc
        2014-01-01 open Income:PnL

        2014-01-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  100 USD
        2014-01-20 price HOUSE  120 USD

        2014-02-10 *
          Assets:Cash           3000 USD
          Assets:Account1       -10 HOUSE {100 USD}
          Income:PnL            -2000 USD

        2014-03-15 *
          Income:Misc           -1000 USD
          Assets:Account1       10 HOUSE {100 USD}

        2014-03-15 price HOUSE  100 USD
        2014-04-15 price HOUSE  120 USD

        """
        # We should have a profit, then clear, then profit
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)
        self.assertEqual(3, len(unreal_entries))
        for target, actual in zip(
                [(None, D('200')), (None, D('-200')), (None, D('200'))],
                unreal_entries):
            if target[0] is not None:
                self.assertEqual(target[0], actual.postings[2].units.number)
            self.assertEqual(target[1], actual.postings[0].units.number)

    @loader.load_doc()
    def test_conversions_only(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc           -780 USD
          Assets:Account1       600 EUR @ 1.3 USD
        """
        # Check to make sure values not held at cost are not included.
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map)
        self.assertEqual([], unrealized_periodic.get_unrealized_entries(new_entries))

    @loader.load_doc()
    def test_with_subaccount(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc
          Assets:Account1       10 HOUSE {100 USD}

        2014-01-15 price HOUSE  101 USD
        """
        entries, errors = unrealized_periodic.add_unrealized_gains(entries, options_map, '_invalid_')
        self.assertEqual([unrealized_periodic.UnrealizedError], list(map(type, errors)))

        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map, 'Gains')
        entries = unrealized_periodic.get_unrealized_entries(new_entries)
        entry = entries[0]
        self.assertEqual('Assets:Account1:Gains', entry.postings[0].account)
        self.assertEqual('Income:Account1:Gains', entry.postings[1].account)

    @loader.load_doc()
    def test_not_assets(self, entries, _, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Liabilities:Account1
        2014-01-01 open Equity:Account1
        2014-01-01 open Expenses:Account1
        2014-01-01 open Income:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc
          Assets:Account1      1 HOUSE {100 USD}
          Liabilities:Account1 2 HOUSE {101 USD}
          Equity:Account1      3 HOUSE {102 USD}
          Expenses:Account1    4 HOUSE {103 USD}
          Income:Account1      5 HOUSE {104 USD}

        2014-01-16 price HOUSE 110 USD
        """
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map, 'Gains')
        unreal_entries = unrealized_periodic.get_unrealized_entries(new_entries)

        entry = get_entries_with_narration(unreal_entries, '1 units')[0]
        self.assertEqual("Assets:Account1:Gains", entry.postings[0].account)
        self.assertEqual("Income:Account1:Gains", entry.postings[1].account)
        self.assertEqual(D("10.00"), entry.postings[0].units.number)
        self.assertEqual(D("-10.00"), entry.postings[1].units.number)

        entry = get_entries_with_narration(unreal_entries, '2 units')[0]
        self.assertEqual("Liabilities:Account1:Gains", entry.postings[0].account)
        self.assertEqual("Income:Account1:Gains", entry.postings[1].account)
        self.assertEqual(D("18.00"), entry.postings[0].units.number)
        self.assertEqual(D("-18.00"), entry.postings[1].units.number)

        entry = get_entries_with_narration(unreal_entries, '3 units')[0]
        self.assertEqual("Equity:Account1:Gains", entry.postings[0].account)
        self.assertEqual("Income:Account1:Gains", entry.postings[1].account)
        self.assertEqual(D("24.00"), entry.postings[0].units.number)
        self.assertEqual(D("-24.00"), entry.postings[1].units.number)

        entry = get_entries_with_narration(unreal_entries, '4 units')[0]
        self.assertEqual("Expenses:Account1:Gains", entry.postings[0].account)
        self.assertEqual("Income:Account1:Gains", entry.postings[1].account)
        self.assertEqual(D("28.00"), entry.postings[0].units.number)
        self.assertEqual(D("-28.00"), entry.postings[1].units.number)

        entry = get_entries_with_narration(unreal_entries, '5 units')[0]
        self.assertEqual("Income:Account1:Gains", entry.postings[0].account)
        self.assertEqual("Income:Account1:Gains", entry.postings[1].account)
        self.assertEqual(D("30.00"), entry.postings[0].units.number)
        self.assertEqual(D("-30.00"), entry.postings[1].units.number)

    @loader.load_doc()
    def test_create_open_directive(self, entries, errors, options_map):
        """
        2014-01-01 open Assets:Account1
        2014-01-01 open Income:Misc

        2014-01-15 *
          Income:Misc
          Assets:Account1      1 HOUSE {100 USD}

        2014-01-16 price HOUSE 110 USD
        """
        # Test the creation of a new, undeclared income account, check that open
        # directives are present for accounts that have been created
        # automatically, because the resulting set of entries should validation
        # no matter what modifications.

        # Test it out without a subaccount, only an open directive should be
        # added for the income account.
        new_entries, errors = unrealized_periodic.add_unrealized_gains(entries, options_map)
        self.assertEqual({'Income:Misc',
                          'Assets:Account1',
                          'Income:Account1'},
                         {entry.account for entry in new_entries
                          if isinstance(entry, data.Open)})

        # Test it with a subaccount; we should observe new open directives for
        # th esubaccounts as well.
        new_entries, _ = unrealized_periodic.add_unrealized_gains(entries, options_map, 'Gains')

        self.assertEqual({'Income:Misc',
                          'Assets:Account1',
                          'Assets:Account1:Gains',
                          'Income:Account1:Gains'},
                         {entry.account for entry in new_entries
                          if isinstance(entry, data.Open)})

        # Validate the new entries; validation should pass.
        valid_errors = validation.validate(new_entries, options_map)
        self.assertFalse(valid_errors)

    @loader.load_doc()
    def test_no_units_but_leaked_cost_basis(self, entries, errors, options_map):
        """
        ;; This probable mistake triggers an error in the unrealized gains
        ;; calculation. This will occur if you use unstrict booking and leak
        ;; some cost basis, resulting in an holding of zero units but some
        ;; non-zero book value (which should be ignored).

        2009-08-17 open Assets:Cash
        2009-08-17 open Assets:Stocks  "NONE"
        2009-08-17 open Income:Stocks

        2009-08-18 * "Bought titles"
          Assets:Cash      -5000 EUR
          Assets:Stocks     5000 HOOL {1.0 EUR}

        2013-06-19 * "Sold with loss"
          Assets:Stocks    -5000 HOOL {1.1 EUR} ;; Incorrect
          Assets:Cash       3385 EUR
          Income:Stocks

        2009-08-18 price HOOL 1.0 EUR
        """
        self.assertFalse(errors)
        new_entries, new_errors = unrealized_periodic.add_unrealized_gains(entries, options_map)
        self.assertFalse(new_errors)
