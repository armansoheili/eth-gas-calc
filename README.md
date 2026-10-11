# eth-gas-calc

An Ethereum transaction gas-cost calculator in pure Python, with zero
dependencies.

It computes the **intrinsic gas** of a transaction (the amount charged before
any contract code runs) and the **EIP-1559 fee math** that turns gas into a
price in ETH.

## Gas rules implemented

| Rule | Value | Source |
|---|---|---|
| Base transaction cost | 21,000 | Yellow Paper |
| Calldata, zero byte | 4 | EIP-2028 |
| Calldata, non-zero byte | 16 | EIP-2028 |
| Contract creation | +32,000 | Yellow Paper |
| Init-code word (32 bytes) | +2 | EIP-3860 |
| Access-list address | 2,400 | EIP-2930 |
| Access-list storage key | 1,900 | EIP-2930 |
| New account creation | +25,000 | Yellow Paper |

Fee math (EIP-1559):

```
effective_gas_price = min(max_fee_per_gas,
                          base_fee_per_gas + max_priority_fee_per_gas)
expected cost = gas_used * effective_gas_price
max cost      = gas_limit * max_fee_per_gas
```

## Usage

```bash
python3 gas_calc.py --demo     # worked examples
python3 gas_calc.py --test     # run the 16 doctests

# ad-hoc query: ERC-20 transfer calldata, current-ish fee market
python3 gas_calc.py --calldata a9059cbb$(python3 -c "print('00'*12 + '11'*20 + '00'*24 + '0de0b6b3a7640000')") \
    --base-fee-gwei 20 --max-priority-gwei 2 --max-fee-gwei 50
```

## Example output

```
== eth-gas-calc demo ==

1. Plain ETH transfer:          21,000 gas
2. ERC-20 transfer calldata:      68 bytes (38 zero, 30 non-zero)
   intrinsic gas:                21,632 gas
3. Contract deployment (1_000B init code + access list):
   intrinsic gas:                75,264 gas
4. EIP-1559 (base 20 / tip 2 / cap 50 gwei, 21_000 gas):
   effective gas price:          22 gwei
   expected cost:                0.000462 ETH (462,000,000,000,000 wei)
   max possible cost:            0.00105 ETH (1,050,000,000,000,000 wei)
```

## Library use

```python
from gas_calc import intrinsic_gas, effective_gas_price, fmt_wei, GWEI

gas = intrinsic_gas(calldata, is_creation=False)          # 21_000 + ...
price = effective_gas_price(20 * GWEI, 50 * GWEI, 2 * GWEI)
print(fmt_wei(gas * price))
```

MIT license — do whatever you want with it.
