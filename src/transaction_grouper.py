from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.currency_converter import CurrencyConverter
from src.models import CakeTransaction, KryptosekkenTransaction
from src.operation_mapper import KryptosekkenTransactionType, OperationMapper


@dataclass
class TransactionGroup:
    """Represents a group of related transactions"""

    transactions: list[CakeTransaction]
    group_type: str  # 'swap', 'daily_rewards', 'single'
    reference_id: str | None = None

    @property
    def timestamp(self) -> datetime:
        """Returns the timestamp of the earliest transaction in the group."""
        return min(tx.date for tx in self.transactions)

    @property
    def total_participants(self) -> int:
        """Get number of transactions in this group"""
        return len(self.transactions)


class TransactionGrouper:
    """
    Groups related CakeDeFi transactions for proper tax reporting.

    Handles:
    1. Swap groups (linked by related_reference_id)
    2. Daily reward aggregation (same day, same operation type)
    3. Single transactions
    """

    def __init__(self, currency_converter: CurrencyConverter):
        self.currency_converter = currency_converter

    def group_transactions(
        self, transactions: list[CakeTransaction]
    ) -> list[TransactionGroup]:
        """Group transactions by reference IDs, split by time gaps, and aggregate rewards."""
        # Filter transactions and preserve order
        filtered_transactions = []
        skipped_count = 0

        for i, tx in enumerate(transactions):
            tx.original_index = i

            # Skip non-taxable transactions
            if OperationMapper.should_skip_transaction(tx.operation, float(tx.amount)):
                skipped_count += 1
                continue

            filtered_transactions.append(tx)

        if skipped_count > 0:
            print(
                f"   🔍 Filtered out {skipped_count} internal staking movements (not taxable)"
            )

        transactions = filtered_transactions

        # Group by reference IDs
        initial_groups = defaultdict(list)
        single_txs = []
        for tx in transactions:
            if tx.related_reference_id and OperationMapper.requires_grouping(
                tx.operation
            ):
                initial_groups[tx.related_reference_id].append(tx)
            else:
                single_txs.append(tx)

        # Attach liquidity result transactions to their groups
        remaining_single_txs = []
        for tx in single_txs:
            if tx.reference and tx.operation in [
                "Added liquidity",
                "Removed liquidity",
            ]:
                # Match by reference field
                if tx.reference in initial_groups:
                    initial_groups[tx.reference].append(tx)
                    # Skip - now grouped
                else:
                    remaining_single_txs.append(tx)
            else:
                remaining_single_txs.append(tx)

        # Update with ungrouped transactions
        single_txs = remaining_single_txs

        # Split groups with large time gaps
        split_groups = []
        MAX_TIME_DELTA = timedelta(minutes=10)
        for _ref_id, tx_list in initial_groups.items():
            if not tx_list:
                continue

            tx_list.sort(key=lambda t: t.date)
            sub_group_txs = [tx_list[0]]
            for i in range(1, len(tx_list)):
                time_gap = tx_list[i].date - tx_list[i - 1].date
                # Large time gap indicates separate events
                if time_gap > MAX_TIME_DELTA:
                    split_groups.append(sub_group_txs)
                    sub_group_txs = [tx_list[i]]
                else:
                    sub_group_txs.append(tx_list[i])
            split_groups.append(sub_group_txs)

        # Create final groups
        final_groups = []
        for tx_list in split_groups:
            group_type = self._determine_group_type(tx_list)
            ref_id = tx_list[0].related_reference_id or tx_list[0].reference
            final_groups.append(TransactionGroup(tx_list, group_type, ref_id))

        # Group rewards
        reward_groups = self._group_daily_rewards(single_txs)
        final_groups.extend(reward_groups)

        # Add remaining single transactions
        grouped_ids = {id(tx) for group in reward_groups for tx in group.transactions}
        for tx in single_txs:
            if id(tx) not in grouped_ids:
                final_groups.append(TransactionGroup([tx], "single"))

        # Sort by time, economic priority, then original order
        final_groups.sort(
            key=lambda g: (
                self._normalize_datetime(g.timestamp),
                self._get_group_economic_priority(g),
                g.transactions[0].original_index,
            )
        )
        return final_groups

    def _normalize_datetime(self, dt: datetime) -> datetime:
        """Convert datetime to UTC for consistent comparison."""
        if dt.tzinfo is None:
            # Treat naive datetime as UTC
            return dt.replace(tzinfo=UTC)
        else:
            # Convert to UTC
            return dt.astimezone(UTC)

    def _get_group_economic_priority(self, group: TransactionGroup) -> int:
        """Economic priority for same-timestamp groups. Lower = higher priority."""
        # Income/Rewards first
        if any(
            OperationMapper.is_income_operation(tx.operation, float(tx.amount))
            for tx in group.transactions
        ):
            return 1

        # Swaps second
        if group.group_type == "swap":
            return 2

        # Liquidity events third
        if group.group_type == "liquidity":
            return 3

        # Everything else last
        return 4

    def _determine_group_type(self, transactions: list[CakeTransaction]) -> str:
        """Determine if a group represents a swap, add liquidity, or remove liquidity event."""
        ops = {tx.operation for tx in transactions}

        # Determine group type from operations
        if any(op.startswith("Add liquidity") or op == "Added liquidity" for op in ops):
            return "add_liquidity"
        if any(
            op.startswith("Remove liquidity") or op == "Removed liquidity" for op in ops
        ):
            return "remove_liquidity"
        # Default to swap
        return "swap"

    def _convert_add_liquidity_group(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        """Convert add liquidity group to kryptosekken transactions."""
        lp_receipt = next(
            (tx for tx in group.transactions if tx.operation == "Added liquidity"), None
        )
        provisions = [
            tx for tx in group.transactions if tx.operation.startswith("Add liquidity")
        ]

        # Complete group: contributions + receipt
        if lp_receipt and len(provisions) >= 1:
            asset1 = provisions[0]
            asset2 = provisions[1] if len(provisions) > 1 else None

            # Convert USD value to NOK for kryptosekken pricing of LP token
            nok_value = self.currency_converter.convert_usd_to_nok(
                abs(lp_receipt.fiat_value), lp_receipt.date
            )
            note = f"Add liquidity (LP token NOK value: {nok_value:.2f})"

            return [
                KryptosekkenTransaction(
                    tidspunkt=lp_receipt.date,
                    type=KryptosekkenTransactionType.HANDEL.value,
                    inn=abs(lp_receipt.amount),
                    inn_valuta=lp_receipt.coin_asset,
                    ut=abs(asset1.amount),
                    ut_valuta=asset1.coin_asset,
                    gebyr=abs(asset2.amount) if asset2 else None,
                    gebyr_valuta=asset2.coin_asset if asset2 else None,
                    marked="CakeDeFi",
                    notat=note,
                )
            ]

        # Incomplete: contributions only
        elif not lp_receipt and len(provisions) > 0:
            # Skip incomplete contributions to avoid double-spending
            return []

        # Incomplete: receipt only
        elif lp_receipt and not provisions:
            # Convert USD value to NOK for kryptosekken pricing
            nok_value = self.currency_converter.convert_usd_to_nok(
                abs(lp_receipt.fiat_value), lp_receipt.date
            )
            note = f"Received LP token (incomplete - assets provided separately) (NOK value: {nok_value:.2f})"

            # Treat LP token receipt as transfer
            return [
                KryptosekkenTransaction(
                    tidspunkt=lp_receipt.date,
                    type=KryptosekkenTransactionType.OVERFORING_INN.value,
                    inn=abs(lp_receipt.amount),
                    inn_valuta=lp_receipt.coin_asset,
                    ut=None,
                    ut_valuta=None,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=note,
                )
            ]

        # Fallback for unexpected format
        return self._fallback_conversion(group)

    def _convert_remove_liquidity_group(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        """Convert remove liquidity group to kryptosekken transactions."""
        # Handle complete remove liquidity groups
        lp_disposal = next(
            (tx for tx in group.transactions if tx.operation == "Removed liquidity"),
            None,
        )
        returns = [
            tx
            for tx in group.transactions
            if tx.operation.startswith("Remove liquidity")
        ]

        if lp_disposal and len(returns) >= 1:
            asset1, asset2 = (
                (returns[0], returns[1]) if len(returns) > 1 else (returns[0], None)
            )

            # Convert USD value to NOK for kryptosekken pricing of LP token
            nok_value = self.currency_converter.convert_usd_to_nok(
                abs(lp_disposal.fiat_value), group.timestamp
            )
            note = f"Remove liquidity (LP token NOK value: {nok_value:.2f})"

            return [
                KryptosekkenTransaction(
                    tidspunkt=group.timestamp,
                    type=KryptosekkenTransactionType.HANDEL.value,
                    inn=abs(asset1.amount),
                    inn_valuta=asset1.coin_asset,
                    ut=abs(lp_disposal.amount),
                    ut_valuta=lp_disposal.coin_asset,
                    gebyr=abs(asset2.amount) if asset2 else None,
                    gebyr_valuta=asset2.coin_asset if asset2 else None,
                    marked="CakeDeFi",
                    notat=note,
                )
            ]
        return self._fallback_conversion(group)

    def _group_swap_transactions(
        self, transactions: list[CakeTransaction]
    ) -> list[TransactionGroup]:
        """Group swap transactions by reference ID."""
        swap_groups = defaultdict(list)

        for tx in transactions:
            if tx.related_reference_id and OperationMapper.requires_grouping(
                tx.operation
            ):
                swap_groups[tx.related_reference_id].append(tx)

        groups = []
        for ref_id, tx_list in swap_groups.items():
            if len(tx_list) > 1:  # Only group if multiple transactions
                # Sort by timestamp within group
                tx_list.sort(key=lambda t: t.date)
                groups.append(TransactionGroup(tx_list, "swap", ref_id))

        return groups

    def _group_daily_rewards(
        self, transactions: list[CakeTransaction]
    ) -> list[TransactionGroup]:
        """Group daily rewards, then aggregate ETH to weekly."""
        # Group by day first
        daily_groups = defaultdict(list)

        for tx in transactions:
            if OperationMapper.is_income_operation(tx.operation, float(tx.amount)):
                # Daily grouping for all currencies
                group_key = (tx.date.date(), tx.coin_asset, "income")
                daily_groups[group_key].append(tx)

        # Create daily groups
        daily_reward_groups = []
        for _group_key, tx_list in daily_groups.items():
            if len(tx_list) > 1:
                # Sort by timestamp
                tx_list.sort(key=lambda t: t.date)
                daily_reward_groups.append(TransactionGroup(tx_list, "daily_rewards"))

        # Aggregate ETH daily groups to weekly
        eth_daily_groups = [
            g for g in daily_reward_groups if g.transactions[0].coin_asset == "ETH"
        ]
        non_eth_groups = [
            g for g in daily_reward_groups if g.transactions[0].coin_asset != "ETH"
        ]

        # Group ETH daily groups by week
        if eth_daily_groups:
            weekly_eth_groups = self._aggregate_eth_daily_to_weekly(eth_daily_groups)
            return non_eth_groups + weekly_eth_groups
        else:
            return non_eth_groups

    def _aggregate_eth_daily_to_weekly(
        self, eth_daily_groups: list[TransactionGroup]
    ) -> list[TransactionGroup]:
        """Aggregate ETH daily groups into weekly groups."""
        weekly_groups = defaultdict(list)

        for daily_group in eth_daily_groups:
            # Get Monday of the week for this daily group
            group_date = daily_group.timestamp.date()
            monday = group_date - timedelta(days=group_date.weekday())

            # Collect all transactions from this daily group
            weekly_groups[monday].extend(daily_group.transactions)

        # Create weekly groups from collected transactions
        weekly_eth_groups = []
        for _monday, tx_list in weekly_groups.items():
            if len(tx_list) > 1:
                # Sort by timestamp
                tx_list.sort(key=lambda t: t.date)
                weekly_eth_groups.append(TransactionGroup(tx_list, "daily_rewards"))

        return weekly_eth_groups

    def convert_group_to_kryptosekken(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        """
        Convert a transaction group to kryptosekken format.

        Args:
            group: TransactionGroup to convert

        Returns:
            List of KryptosekkenTransaction objects (usually 1, sometimes more for complex swaps)
        """
        if group.group_type == "swap":
            return self._convert_swap_group(group)
        elif group.group_type == "add_liquidity":
            return self._convert_add_liquidity_group(group)
        elif group.group_type == "remove_liquidity":
            return self._convert_remove_liquidity_group(group)
        elif group.group_type == "daily_rewards":
            return self._convert_daily_rewards_group(group)
        else:  # single transaction
            return self._convert_single_transaction(group.transactions[0])

    def _convert_swap_group(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        """Convert swap group by netting intermediate assets."""
        from collections import defaultdict
        from decimal import Decimal

        # Categorize transaction flows
        incoming_txs = defaultdict(Decimal)
        outgoing_txs = defaultdict(Decimal)
        fee_txs = defaultdict(Decimal)
        conversion_op_str = None

        for tx in group.transactions:
            if tx.operation == "Paid swap fee":
                fee_txs[tx.coin_asset] += abs(tx.amount)
            elif tx.amount < 0:
                outgoing_txs[tx.coin_asset] += abs(tx.amount)
            elif tx.amount > 0:
                incoming_txs[tx.coin_asset] += tx.amount

            if "Converted" in tx.operation:
                conversion_op_str = tx.operation

        # Net out intermediate assets
        for currency in list(incoming_txs.keys()):
            if currency in outgoing_txs or currency in fee_txs:
                total_in = incoming_txs[currency]
                total_out = outgoing_txs.get(currency, Decimal("0")) + fee_txs.get(
                    currency, Decimal("0")
                )
                net_amount = total_in - total_out

                # Use tolerance for Decimal comparison
                if abs(net_amount) < Decimal("1e-9"):
                    incoming_txs.pop(currency, None)
                    outgoing_txs.pop(currency, None)
                    fee_txs.pop(currency, None)

        # Create final trade transaction

        # Standard swap: clear inputs and outputs
        if len(incoming_txs) == 1 and len(outgoing_txs) >= 1:
            inn_valuta, inn_amount = list(incoming_txs.items())[0]
            ut_valuta, ut_amount = list(outgoing_txs.items())[0]
            gebyr_valuta, gebyr_amount = (
                (list(fee_txs.items())[0]) if fee_txs else (None, None)
            )

            return [
                KryptosekkenTransaction(
                    tidspunkt=group.timestamp,
                    type="Handel",
                    inn=inn_amount,
                    inn_valuta=inn_valuta,
                    ut=ut_amount,
                    ut_valuta=ut_valuta,
                    gebyr=gebyr_amount,
                    gebyr_valuta=gebyr_valuta,
                    marked="CakeDeFi",
                    notat=f"Swap from {len(group.transactions)} txs",
                )
            ]

        # Internal conversions (not taxable)
        elif len(incoming_txs) == 1 and not outgoing_txs and conversion_op_str:
            inn_valuta, inn_amount = list(incoming_txs.items())[0]

            # Convert USD value to NOK for tax reference
            total_inn_value_usd = sum(
                tx.fiat_value for tx in group.transactions if tx.amount > 0
            )
            nok_value = self.currency_converter.convert_usd_to_nok(
                abs(total_inn_value_usd), group.timestamp
            )

            # Internal conversions treated as income (no taxable disposal)
            simple_op = conversion_op_str.replace("Converted ", "").replace(" to ", "→")
            note = f"{simple_op} (NOK value: {nok_value:.2f})"

            return [
                KryptosekkenTransaction(
                    tidspunkt=group.timestamp,
                    type=KryptosekkenTransactionType.INNTEKT.value,
                    inn=inn_amount,
                    inn_valuta=inn_valuta,
                    ut=None,
                    ut_valuta=None,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=note,
                )
            ]

        # Fallback for unresolvable groups
        return self._fallback_conversion(group)

    def _fallback_conversion(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        print(
            f"WARNING: Complex/unresolvable group at {group.timestamp}. Processing as individual txs."
        )
        return [
            tx
            for sublist in [
                self._convert_single_transaction(tx) for tx in group.transactions
            ]
            for tx in sublist
        ]

    def _convert_daily_rewards_group(
        self, group: TransactionGroup
    ) -> list[KryptosekkenTransaction]:
        """Convert rewards group to single aggregated transaction."""
        # Sum up all amounts in the group
        total_amount = sum(tx.amount for tx in group.transactions)

        # Use the first transaction as template
        template_tx = group.transactions[0]

        # Calculate NOK value using each transaction's date

        total_nok_value = Decimal("0")
        for tx in group.transactions:
            # Convert USD to NOK for each transaction
            tx_nok_value = self.currency_converter.convert_usd_to_nok(
                abs(tx.fiat_value),
                tx.date,
            )
            total_nok_value += tx_nok_value

        # Create note with appropriate timeframe (weekly for ETH, daily for others)
        timeframe = "Weekly" if template_tx.coin_asset == "ETH" else "Daily"
        note = f"{timeframe} {template_tx.coin_asset} rewards {len(group.transactions)} txs (NOK value: {total_nok_value:.2f})"

        return [
            KryptosekkenTransaction(
                tidspunkt=group.timestamp,
                type=KryptosekkenTransactionType.INNTEKT.value,
                inn=abs(total_amount),
                inn_valuta=template_tx.coin_asset,
                ut=None,
                ut_valuta=None,
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat=note,
            )
        ]

    def _convert_single_transaction(
        self, tx: CakeTransaction
    ) -> list[KryptosekkenTransaction]:
        """Convert single transaction to kryptosekken format."""
        tx_type = OperationMapper.get_transaction_type(tx.operation, float(tx.amount))

        # Convert USD value to NOK
        nok_value = self.currency_converter.convert_usd_to_nok(
            abs(tx.fiat_value), tx.date
        )

        # Create simple note without special characters
        def simplify_operation(op: str) -> str:
            # Keep only alphanumeric characters
            import re

            simplified = re.sub(r"[^a-zA-Z0-9\s]", "", op)
            # Limit to 30 characters
            if len(simplified) > 30:
                simplified = simplified[:30]
            return simplified.strip()

        simple_note = simplify_operation(tx.operation)

        if tx_type == KryptosekkenTransactionType.INNTEKT:
            # Income: receive crypto (NOK value for tax reference only)
            nok_note = (
                f"{simple_note} (NOK value: {nok_value:.2f})"
                if nok_value
                else simple_note
            )
            return [
                KryptosekkenTransaction(
                    tidspunkt=tx.date,
                    type=tx_type.value,
                    inn=abs(tx.amount),
                    inn_valuta=tx.coin_asset,
                    ut=None,
                    ut_valuta=None,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=nok_note,
                )
            ]

        elif tx_type == KryptosekkenTransactionType.OVERFORING_INN:
            # Transfer in: receive crypto
            return [
                KryptosekkenTransaction(
                    tidspunkt=tx.date,
                    type=tx_type.value,
                    inn=abs(tx.amount),
                    inn_valuta=tx.coin_asset,
                    ut=None,
                    ut_valuta=None,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=simple_note,
                )
            ]

        elif tx_type == KryptosekkenTransactionType.OVERFORING_UT:
            # Transfer out: send crypto
            return [
                KryptosekkenTransaction(
                    tidspunkt=tx.date,
                    type=tx_type.value,
                    inn=None,
                    inn_valuta=None,
                    ut=abs(tx.amount),
                    ut_valuta=tx.coin_asset,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=simple_note,
                )
            ]

        elif tx_type == KryptosekkenTransactionType.FORVALTNINGSKOSTNAD:
            # Management fee: cost in crypto
            return [
                KryptosekkenTransaction(
                    tidspunkt=tx.date,
                    type=tx_type.value,
                    inn=None,
                    inn_valuta=None,
                    ut=abs(tx.amount),
                    ut_valuta=tx.coin_asset,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=simple_note,
                )
            ]

        else:
            # Handle operations that shouldn't be individual trades
            problematic_operations = [
                "Add liquidity",
                "Remove liquidity",
                "Entered Earn",
                "Exited Earn",
            ]

            is_problematic = any(
                tx.operation.startswith(op) for op in problematic_operations
            )

            if is_problematic:
                # Treat ungrouped DeFi operations as transfers
                if tx.amount < 0:
                    # Outgoing transfer
                    return [
                        KryptosekkenTransaction(
                            tidspunkt=tx.date,
                            type=KryptosekkenTransactionType.OVERFORING_UT.value,
                            inn=None,
                            inn_valuta=None,
                            ut=abs(tx.amount),
                            ut_valuta=tx.coin_asset,
                            gebyr=None,
                            gebyr_valuta=None,
                            marked="CakeDeFi",
                            notat=f"{simple_note} (incomplete DeFi op)",
                        )
                    ]
                else:
                    # Incoming transfer
                    return [
                        KryptosekkenTransaction(
                            tidspunkt=tx.date,
                            type=KryptosekkenTransactionType.OVERFORING_INN.value,
                            inn=abs(tx.amount),
                            inn_valuta=tx.coin_asset,
                            ut=None,
                            ut_valuta=None,
                            gebyr=None,
                            gebyr_valuta=None,
                            marked="CakeDeFi",
                            notat=f"{simple_note} (incomplete DeFi op)",
                        )
                    ]

            # Default case: trade-like transaction
            return [
                KryptosekkenTransaction(
                    tidspunkt=tx.date,
                    type=tx_type.value,
                    inn=abs(tx.amount) if tx.amount > 0 else None,
                    inn_valuta=tx.coin_asset if tx.amount > 0 else None,
                    ut=abs(tx.amount) if tx.amount < 0 else None,
                    ut_valuta=tx.coin_asset if tx.amount < 0 else None,
                    gebyr=None,
                    gebyr_valuta=None,
                    marked="CakeDeFi",
                    notat=simple_note,
                )
            ]
