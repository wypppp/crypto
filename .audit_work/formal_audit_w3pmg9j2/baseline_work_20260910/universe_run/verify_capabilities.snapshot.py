#!/usr/bin/env python3
"""Right-tail preflight v2.0, 2026-09-09. Read-only; never sends a transaction.

run dependencies: python -m pip install 'eth-hash[pycryptodome]'
selftest additionally: python -m pip install eth-tester py-evm
Usage:
  python verify_capabilities.py selftest --out offline_verification.json
  python verify_capabilities.py run --out verification_log.json
  (run reads ETH_RPC_URL locally; --rpc is also accepted.)

[文档确认] S1/S2/S3: canonical V2 factory registry, locked minimum LP supply,
fee-supporting router methods without returns; ordinary swap amounts are quotes.
[推论·源码推导] On canonical V2, totalSupply>0 is monotone after first Mint;
reserves>0 is neither monotone nor equivalent to first Mint. Logs cross-check it.
[文档确认] S4: eth_call overrides are ephemeral; code/stateDiff/balance exist.
[设计选择] This script uses an injected CONTRACT wallet and two historical
snapshots. It does not reproduce EOA identity checks, holding-period state,
intervening transactions, transaction inclusion or a 30-day strategy return.
[假设·未验证] A token's balance mapping slot alone suffices ONLY for the limited
exit capability probe. Candidate-specific state semantics remain a separate gate.
[端点实测] Only run-mode logs can use this label, for the recorded endpoint,
blocks, code hashes, wallet, overrides and calls. selftest is local EVM evidence.

S1 https://github.com/Uniswap/v2-core/blob/master/contracts/UniswapV2Factory.sol
S2 https://github.com/Uniswap/v2-core/blob/master/contracts/UniswapV2Pair.sol
S3 https://github.com/Uniswap/v2-periphery/blob/master/contracts/UniswapV2Router02.sol
S4 https://geth.ethereum.org/docs/interacting-with-geth/rpc/objects
S5 https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-get-logs

The Solidity source and compiled runtimes below are embedded for reproducibility.
Compiler: solc 0.8.26, optimizer runs=200, evmVersion=istanbul, bytecodeHash=none.
Controlled fixtures are artificial instruments, never market observations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2.0"
FACTORY = "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"
ROUTER = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
DAI = "0x6b175474e89094c44da98b954eedeac495271d0f"
# Virtual identities; no private key, account connection or user identity required.
WALLET = "0x00000000000000000000000000000000ba5e1001"
CALLER = "0x00000000000000000000000000000000ba5e1002"
CONTROL_TOKEN = "0x00000000000000000000000000000000ba5e1003"
CONTROL_ROUTER = "0x00000000000000000000000000000000ba5e1004"
ZERO = "0x" + "00" * 20
AMOUNT = 50_000_000_000_000_000  # 0.05 ETH, exact integer wei
DAY = 86400
# Independent published ABI vectors; never used as a hashing fallback.
SELECTORS = {
    "allPairsLength()": "574f2ba3", "allPairs(uint256)": "1e3dd18b",
    "token0()": "0dfe1681", "token1()": "d21220a7",
    "totalSupply()": "18160ddd", "getReserves()": "0902f1ac",
    "balanceOf(address)": "70a08231", "decimals()": "313ce567",
    "getPair(address,address)": "e6a43905", "allowance(address,address)": "dd62ed3e",
    "approve(address,uint256)": "095ea7b3",
}
TOPICS = {
    "Mint(address,uint256,uint256)": "4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f",
    "PairCreated(address,address,address,uint256)": "0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9",
}

SOLIDITY_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
interface Token {
    function balanceOf(address) external view returns(uint256);
    function allowance(address,address) external view returns(uint256);
}
// Ephemeral instrumentation wallet. It is a CONTRACT wallet, not an EOA model.
contract Probe {
    uint256 public marker;
    receive() external payable {}
    function inspect() external view returns(uint256,uint256) {
        return(address(this).balance,marker);
    }
    function buy(address token,address router,uint256 amount,uint256 deadline)
        external returns(uint256 stage,uint256 b0,uint256 b1,uint256 e0,uint256 e1,bytes memory reason) {
        b0=Token(token).balanceOf(address(this)); e0=address(this).balance;
        address[] memory path=new address[](2);
        path[0]=0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2; path[1]=token;
        (bool ok,bytes memory data)=router.call{value:amount}(abi.encodeWithSignature(
            "swapExactETHForTokensSupportingFeeOnTransferTokens(uint256,address[],address,uint256)",0,path,address(this),deadline));
        b1=Token(token).balanceOf(address(this)); e1=address(this).balance;
        return(ok?0:20,b0,b1,e0,e1,data);
    }
    function sell(address token,address router,uint256 amount,uint256 deadline,bool doApprove)
        external returns(uint256 stage,uint256 b0,uint256 b1,uint256 e0,uint256 e1,bytes memory reason) {
        b0=Token(token).balanceOf(address(this)); e0=address(this).balance;
        if(b0<amount) return(10,b0,b0,e0,e0,bytes("balance"));
        if(doApprove) {
            (bool ok0,bytes memory d0)=token.call(abi.encodeWithSignature("approve(address,uint256)",router,0));
            if(!ok0 || (d0.length!=0 && (d0.length!=32 || !abi.decode(d0,(bool)))))
                return(12,b0,b0,e0,e0,d0);
            (bool ok1,bytes memory d1)=token.call(abi.encodeWithSignature("approve(address,uint256)",router,amount));
            if(!ok1 || (d1.length!=0 && (d1.length!=32 || !abi.decode(d1,(bool)))))
                return(12,b0,b0,e0,e0,d1);
        }
        if(Token(token).allowance(address(this),router)<amount)
            return(11,b0,b0,e0,e0,bytes("allowance"));
        address[] memory path=new address[](2);
        path[0]=token; path[1]=0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
        (bool ok,bytes memory data)=router.call(abi.encodeWithSignature(
            "swapExactTokensForETHSupportingFeeOnTransferTokens(uint256,uint256,address[],address,uint256)",
            amount,0,path,address(this),deadline));
        b1=Token(token).balanceOf(address(this)); e1=address(this).balance;
        return(ok?0:20,b0,b1,e0,e1,data);
    }
}
// Artificial controls only. These contracts make NO claim about a real token.
contract FixtureToken {
    mapping(address=>uint256) public balanceOf; // slot 0
    mapping(address=>mapping(address=>uint256)) public allowance; // slot 1
    uint256 public taxBps; // slot 2
    bool public restricted; // slot 3
    error InsufficientBalance(); error InsufficientAllowance(); error SellRestricted();
    function mint(address who,uint256 amount) external { balanceOf[who]+=amount*(10000-taxBps)/10000; }
    function approve(address spender,uint256 amount) external returns(bool) { allowance[msg.sender][spender]=amount; return true; }
    function transferFrom(address from,address to,uint256 amount) external returns(bool) {
        if(restricted) revert SellRestricted();
        if(balanceOf[from]<amount) revert InsufficientBalance();
        if(allowance[from][msg.sender]<amount) revert InsufficientAllowance();
        allowance[from][msg.sender]-=amount; balanceOf[from]-=amount;
        balanceOf[to]+=amount*(10000-taxBps)/10000; return true;
    }
}
contract FixtureRouter {
    receive() external payable {}
    function swapExactETHForTokensSupportingFeeOnTransferTokens(uint256,address[] calldata path,address to,uint256) external payable {
        FixtureToken(path[1]).mint(to,msg.value*10);
    }
    function swapExactTokensForETHSupportingFeeOnTransferTokens(uint256 amount,uint256,address[] calldata path,address to,uint256) external {
        FixtureToken t=FixtureToken(path[0]); uint256 b0=t.balanceOf(address(this));
        t.transferFrom(msg.sender,address(this),amount);
        uint256 got=t.balanceOf(address(this))-b0;
        (bool ok,)=to.call{value:got/10}(""); require(ok,"pay");
    }
}
"""
RUNTIMES = {'FixtureRouter': '0x60806040526004361061002d5760003560e01c8063791ac94714610039578063b6f9de951461005b57600080fd5b3661003457005b600080fd5b34801561004557600080fd5b506100596100543660046103a8565b61006e565b005b61005961006936600461041a565b610299565b60008484600081811061008357610083610480565b90506020020160208101906100989190610496565b6040516370a0823160e01b81523060048201529091506000906001600160a01b038316906370a0823190602401602060405180830381865afa1580156100e2573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061010691906104b8565b6040516323b872dd60e01b8152336004820152306024820152604481018a90529091506001600160a01b038316906323b872dd906064016020604051808303816000875af115801561015c573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061018091906104d1565b506040516370a0823160e01b815230600482015260009082906001600160a01b038516906370a0823190602401602060405180830381865afa1580156101ca573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906101ee91906104b8565b6101f89190610509565b905060006001600160a01b038616610211600a84610522565b604051600081818185875af1925050503d806000811461024d576040519150601f19603f3d011682016040523d82523d6000602084013e610252565b606091505b505090508061028d5760405162461bcd60e51b815260206004820152600360248201526270617960e81b604482015260640160405180910390fd5b50505050505050505050565b838360018181106102ac576102ac610480565b90506020020160208101906102c19190610496565b6001600160a01b03166340c10f19836102db34600a610544565b6040516001600160e01b031960e085901b1681526001600160a01b0390921660048301526024820152604401600060405180830381600087803b15801561032157600080fd5b505af1158015610335573d6000803e3d6000fd5b505050505050505050565b60008083601f84011261035257600080fd5b50813567ffffffffffffffff81111561036a57600080fd5b6020830191508360208260051b850101111561038557600080fd5b9250929050565b80356001600160a01b03811681146103a357600080fd5b919050565b60008060008060008060a087890312156103c157600080fd5b8635955060208701359450604087013567ffffffffffffffff8111156103e657600080fd5b6103f289828a01610340565b909550935061040590506060880161038c565b95989497509295919493608090920135925050565b60008060008060006080868803121561043257600080fd5b85359450602086013567ffffffffffffffff81111561045057600080fd5b61045c88828901610340565b909550935061046f90506040870161038c565b949793965091946060013592915050565b634e487b7160e01b600052603260045260246000fd5b6000602082840312156104a857600080fd5b6104b18261038c565b9392505050565b6000602082840312156104ca57600080fd5b5051919050565b6000602082840312156104e357600080fd5b815180151581146104b157600080fd5b634e487b7160e01b600052601160045260246000fd5b8181038181111561051c5761051c6104f3565b92915050565b60008261053f57634e487b7160e01b600052601260045260246000fd5b500490565b808202811582820484141761051c5761051c6104f356fea164736f6c634300081a000a', 'FixtureToken': '0x608060405234801561001057600080fd5b506004361061007d5760003560e01c806340c10f191161005b57806340c10f19146100d45780637072c6b1146100e957806370a08231146100f6578063dd62ed3e1461011657600080fd5b8063095ea7b31461008257806323b872dd146100aa5780633eacd2f8146100bd575b600080fd5b610095610090366004610348565b610141565b60405190151581526020015b60405180910390f35b6100956100b8366004610372565b61016f565b6100c660025481565b6040519081526020016100a1565b6100e76100e2366004610348565b6102d4565b005b6003546100959060ff1681565b6100c66101043660046103af565b60006020819052908152604090205481565b6100c66101243660046103d1565b600160209081526000928352604080842090915290825290205481565b3360009081526001602081815260408084206001600160a01b03871685529091529091208290555b92915050565b60035460009060ff1615610196576040516339666cf760e01b815260040160405180910390fd5b6001600160a01b0384166000908152602081905260409020548211156101cf57604051631e9acf1760e31b815260040160405180910390fd5b6001600160a01b0384166000908152600160209081526040808320338452909152902054821115610213576040516313be252b60e01b815260040160405180910390fd5b6001600160a01b03841660009081526001602090815260408083203384529091528120805484929061024690849061041a565b90915550506001600160a01b0384166000908152602081905260408120805484929061027390849061041a565b909155505060025461271090610289908261041a565b610293908461042d565b61029d9190610444565b6001600160a01b038416600090815260208190526040812080549091906102c5908490610466565b90915550600195945050505050565b6127106002546127106102e7919061041a565b6102f1908361042d565b6102fb9190610444565b6001600160a01b03831660009081526020819052604081208054909190610323908490610466565b90915550505050565b80356001600160a01b038116811461034357600080fd5b919050565b6000806040838503121561035b57600080fd5b6103648361032c565b946020939093013593505050565b60008060006060848603121561038757600080fd5b6103908461032c565b925061039e6020850161032c565b929592945050506040919091013590565b6000602082840312156103c157600080fd5b6103ca8261032c565b9392505050565b600080604083850312156103e457600080fd5b6103ed8361032c565b91506103fb6020840161032c565b90509250929050565b634e487b7160e01b600052601160045260246000fd5b8181038181111561016957610169610404565b808202811582820484141761016957610169610404565b60008261046157634e487b7160e01b600052601260045260246000fd5b500490565b808201808211156101695761016961040456fea164736f6c634300081a000a', 'Probe': '0x6080604052600436106100425760003560e01c8062a4b3621461004e5780633acddfc114610089578063a44c9180146100ad578063a9d424e2146100d957600080fd5b3661004957005b600080fd5b34801561005a57600080fd5b5061006e61006936600461089c565b6100f9565b6040516100809695949392919061091b565b60405180910390f35b34801561009557600080fd5b5061009f60005481565b604051908152602001610080565b3480156100b957600080fd5b506100c46000544791565b60408051928352602083019190915201610080565b3480156100e557600080fd5b5061006e6100f4366004610971565b61061f565b6040516370a0823160e01b815230600482015260009081908190819081906060906001600160a01b038c16906370a0823190602401602060405180830381865afa15801561014b573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061016f91906109b3565b9450479250888510156101aa57505060408051808201909152600781526662616c616e636560c81b6020820152600a94508392508190610612565b86156103a2576040516001600160a01b038b811660248301526000604483018190529182918e169060640160408051601f198184030181529181526020820180516001600160e01b031663095ea7b360e01b1790525161020a91906109cc565b6000604051808303816000865af19150503d8060008114610247576040519150601f19603f3d011682016040523d82523d6000602084013e61024c565b606091505b5091509150811580610286575080511580159061028657508051602014158061028657508080602001905181019061028491906109e8565b155b1561029e57600c975086955084935091506106129050565b6000808e6001600160a01b03168e8e6040516024016102d29291906001600160a01b03929092168252602082015260400190565b60408051601f198184030181529181526020820180516001600160e01b031663095ea7b360e01b1790525161030791906109cc565b6000604051808303816000865af19150503d8060008114610344576040519150601f19603f3d011682016040523d82523d6000602084013e610349565b606091505b5091509150811580610383575080511580159061038357508051602014158061038357508080602001905181019061038191906109e8565b155b1561039d57600c9950889750869550935061061292505050565b505050505b604051636eb1769f60e11b81523060048201526001600160a01b038b811660248301528a91908d169063dd62ed3e90604401602060405180830381865afa1580156103f1573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061041591906109b3565b101561044b575050604080518082019091526009815268616c6c6f77616e636560b81b6020820152600b94508392508190610612565b6040805160028082526060820183526000926020830190803683370190505090508b8160008151811061048057610480610a0c565b60200260200101906001600160a01b031690816001600160a01b03168152505073c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2816001815181106104c8576104c8610a0c565b60200260200101906001600160a01b031690816001600160a01b0316815250506000808c6001600160a01b03168c600085308f60405160240161050f959493929190610a67565b60408051601f198184030181529181526020820180516001600160e01b031663791ac94760e01b1790525161054491906109cc565b6000604051808303816000865af19150503d8060008114610581576040519150601f19603f3d011682016040523d82523d6000602084013e610586565b606091505b506040516370a0823160e01b815230600482015291935091506001600160a01b038f16906370a0823190602401602060405180830381865afa1580156105d0573d6000803e3d6000fd5b505050506040513d601f19601f820116820180604052508101906105f491906109b3565b965047945081610605576014610608565b60005b60ff169850925050505b9550955095509550955095565b6040516370a0823160e01b815230600482015260009081908190819081906060906001600160a01b038b16906370a0823190602401602060405180830381865afa158015610671573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061069591906109b3565b604080516002808252606082018352929750479550600092909160208301908036833701905050905073c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2816000815181106106e6576106e6610a0c565b60200260200101906001600160a01b031690816001600160a01b0316815250508a8160018151811061071a5761071a610a0c565b60200260200101906001600160a01b031690816001600160a01b0316815250506000808b6001600160a01b03168b600085308e6040516024016107609493929190610aa6565b60408051601f198184030181529181526020820180516001600160e01b031663b6f9de9560e01b1790525161079591906109cc565b60006040518083038185875af1925050503d80600081146107d2576040519150601f19603f3d011682016040523d82523d6000602084013e6107d7565b606091505b506040516370a0823160e01b815230600482015291935091506001600160a01b038e16906370a0823190602401602060405180830381865afa158015610821573d6000803e3d6000fd5b505050506040513d601f19601f8201168201806040525081019061084591906109b3565b965047945081610856576014610859565b60005b60ff169850925050509499939850945094509450565b80356001600160a01b038116811461088657600080fd5b919050565b801515811461089957600080fd5b50565b600080600080600060a086880312156108b457600080fd5b6108bd8661086f565b94506108cb6020870161086f565b9350604086013592506060860135915060808601356108e98161088b565b809150509295509295909350565b60005b838110156109125781810151838201526020016108fa565b50506000910152565b86815285602082015284604082015283606082015282608082015260c060a0820152600082518060c08401526109588160e08501602087016108f7565b601f01601f19169190910160e001979650505050505050565b6000806000806080858703121561098757600080fd5b6109908561086f565b935061099e6020860161086f565b93969395505050506040820135916060013590565b6000602082840312156109c557600080fd5b5051919050565b600082516109de8184602087016108f7565b9190910192915050565b6000602082840312156109fa57600080fd5b8151610a058161088b565b9392505050565b634e487b7160e01b600052603260045260246000fd5b600081518084526020840193506020830160005b82811015610a5d5781516001600160a01b0316865260209586019590910190600101610a36565b5093949350505050565b85815260ff8516602082015260a060408201526000610a8960a0830186610a22565b6001600160a01b0394909416606083015250608001529392505050565b60ff85168152608060208201526000610ac26080830186610a22565b6001600160a01b0394909416604083015250606001529291505056fea164736f6c634300081a000a'}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def keccak(data: bytes) -> bytes:
    try:
        from eth_hash.auto import keccak as implementation
        return implementation(data)
    except ImportError as exc:
        raise RuntimeError("Missing keccak backend: install eth-hash[pycryptodome]") from exc


def selector(signature):
    return keccak(signature.encode())[:4].hex()


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("Expected a 20-byte hex address")
    return value.lower()


def raw_hex(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("Expected an even-length 0x-prefixed byte string")
    return bytes.fromhex(value[2:])


def quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise ValueError("Invalid JSON-RPC quantity")
    return int(value, 16)


def pad(value):
    if isinstance(value, str):
        if not re.fullmatch(r"0x[0-9a-fA-F]+", value):
            raise ValueError("Expected hex integer")
        value = int(value, 16)
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 2**256:
        raise ValueError("Integer outside uint256")
    return f"{value:064x}"


def words(value, count):
    data = raw_hex(value)
    if len(data) != count * 32:
        raise ValueError(f"ABI result requires {count * 32} bytes, got {len(data)}")
    return [int.from_bytes(data[i:i+32], "big") for i in range(0, len(data), 32)]


def word(value):
    return words(value, 1)[0]


def addr_from_word(value):
    v = word(value)
    if v >= 2**160:
        raise ValueError("Nonzero high bytes in ABI address")
    return f"0x{v:040x}"


def calldata(signature, *values):
    return "0x" + selector(signature) + "".join(pad(int(v) if isinstance(v, bool) else v) for v in values)


def mapping_key(owner, slot):
    return "0x" + keccak(bytes.fromhex(pad(address(owner)) + pad(slot))).hex()


def parse_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.microsecond:
        raise ValueError("Use timezone-aware timestamps with whole seconds")
    return int(dt.timestamp())


def first_true(lo, hi, predicate):
    """Requires a monotone predicate and verified false/true endpoints."""
    if lo < 0 or lo >= hi or predicate(lo) or not predicate(hi):
        raise ValueError("Binary search is not bracketed by false and true")
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if predicate(mid):
            hi = mid
        else:
            lo = mid
    return hi


def parse_probe(value):
    data = raw_hex(value)
    if len(data) < 224 or len(data) % 32:
        raise ValueError("Malformed probe return")
    head = [int.from_bytes(data[i:i+32], "big") for i in range(0, 192, 32)]
    if head[5] != 192:
        raise ValueError("Unexpected probe bytes offset")
    length = int.from_bytes(data[192:224], "big")
    if len(data) != 224 + ((length + 31)//32)*32:
        raise ValueError("Truncated or oversized probe return")
    return dict(zip(("stage", "token_before", "token_after", "eth_before", "eth_after"), head[:5]),
                reason="0x" + data[224:224+length].hex())


def classify_probe(result):
    # A generic revert NEVER becomes an 'unsellable' market label.
    return {0: "simulated_success", 10: "environment_missing_balance",
            11: "environment_missing_allowance", 12: "approval_failed_unknown",
            20: "execution_reverted_unknown"}.get(result["stage"], "unknown_probe_stage")


class RpcFailure(RuntimeError):
    def __init__(self, kind, message, code=None):
        super().__init__(message)
        self.kind, self.code = kind, code


class Unrun(RuntimeError):
    pass


def validate_envelope(obj, request_id):
    if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0" or obj.get("id") != request_id:
        raise RpcFailure("protocol", "Malformed or mismatched JSON-RPC envelope")
    if ("result" in obj) == ("error" in obj):
        raise RpcFailure("protocol", "Expected exactly one of result/error")
    if "error" in obj:
        e = obj["error"]
        if not isinstance(e, dict):
            raise RpcFailure("protocol", "Malformed JSON-RPC error")
        raise RpcFailure("rpc", str(e.get("message", "RPC error")), e.get("code"))
    if obj["result"] is None:
        raise RpcFailure("missing_result", "RPC returned null")
    return obj["result"]


class RPC:
    ALLOWED = {"eth_chainId", "eth_getBlockByNumber", "eth_getCode", "eth_call", "eth_getLogs", "eth_getBalance"}

    def __init__(self, url, *, max_calls=700, max_seconds=600, timeout=20, rps=3):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise ValueError("RPC URL must be HTTP(S)")
        if parsed.username or parsed.password:
            raise ValueError("Use an endpoint without URL userinfo")
        self.url, self.host = url, parsed.hostname
        self.secrets = {url}
        self.secrets.update(x for x in parsed.path.split("/") if len(x) >= 12)
        self.secrets.update(v for _, v in urllib.parse.parse_qsl(parsed.query) if v)
        self.max_calls, self.max_seconds, self.timeout, self.interval = max_calls, max_seconds, timeout, 1/rps
        self.started = time.monotonic()
        self.last = 0.0
        self.records = []

    def redact(self, value):
        if isinstance(value, dict):
            return {k: self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            for secret in sorted(self.secrets, key=len, reverse=True):
                value = value.replace(secret, "[redacted]")
            return re.sub(r"https?://[^\s\"'<>]+", "[redacted-url]", value)
        return value

    def request(self, method, params):
        if method not in self.ALLOWED:
            raise RpcFailure("forbidden_method", "Method is outside read-only allowlist")
        for attempt in range(2):
            elapsed = time.monotonic() - self.started
            if len(self.records) >= self.max_calls or elapsed >= self.max_seconds:
                raise RpcFailure("budget", "RPC call/time budget exhausted")
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
            remaining = self.max_seconds - (time.monotonic() - self.started)
            if remaining <= 0:
                raise RpcFailure("budget", "RPC time budget exhausted")
            rid = len(self.records) + 1
            item = {"id": rid, "method": method, "params": json.loads(json.dumps(params)), "observed_at": utcnow(), "attempt": attempt + 1}
            started = time.monotonic()
            try:
                req = urllib.request.Request(self.url, data=json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=min(self.timeout, remaining)) as response:
                    payload = response.read(4 * 1024 * 1024 + 1)
                    if len(payload) > 4 * 1024 * 1024:
                        raise RpcFailure("response_limit", "Probe response exceeds 4 MiB")
                    obj = json.loads(payload)
                item["response"] = self.redact(obj)
                result = validate_envelope(obj, rid)
                item["status"] = "OK"
                return result
            except urllib.error.HTTPError as exc:
                item["error"] = {"kind": "http", "code": exc.code}
                if exc.code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(1)
                    continue
                raise RpcFailure("http", f"HTTP {exc.code}", exc.code) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                item["error"] = {"kind": "transport", "message": self.redact(str(exc))}
                raise RpcFailure("transport", self.redact(str(exc))) from None
            except (json.JSONDecodeError, UnicodeError) as exc:
                item["error"] = {"kind": "protocol", "message": type(exc).__name__}
                raise RpcFailure("protocol", "Non-JSON RPC response") from None
            except RpcFailure as exc:
                item["error"] = {"kind": exc.kind, "code": exc.code, "message": self.redact(str(exc))}
                raise
            finally:
                self.last = time.monotonic()
                item["elapsed_s"] = round(self.last - started, 6)
                self.records.append(self.redact(item))
        raise AssertionError("Retry exhausted")

    def call(self, to, data, block, overrides=None):
        tx = {"from": CALLER, "to": address(to), "data": data, "gas": hex(8_000_000)}
        params = [tx, hex(block)]
        if overrides is not None:
            params.append(overrides)
        return self.request("eth_call", params)


class Report:
    def __init__(self, mode):
        self.doc = {"schema": "right-tail-preflight/2", "script_version": VERSION, "mode": mode,
                    "started_at": utcnow(), "results": [], "baseline_ready": False,
                    "scope": "capability probe only; no market return or strategy conclusion"}

    def check(self, tid, name, function, required=True):
        start = time.monotonic()
        try:
            detail = function()
            item = {"id": tid, "name": name, "status": "PASS", "detail": detail}
        except Unrun as exc:
            item = {"id": tid, "name": name, "status": "UNRUN", "detail": {"reason": str(exc)}}
        except Exception as exc:
            item = {"id": tid, "name": name, "status": "FAIL", "detail": {"error_type": type(exc).__name__, "message": str(exc)}}
            if isinstance(exc, RpcFailure):
                item["detail"].update(kind=exc.kind, code=exc.code)
        item.update(required=required, elapsed_s=round(time.monotonic()-start, 6))
        self.doc["results"].append(item)
        # Raw errors and URLs stay out of stdout; sanitized evidence is in the log.
        print(f"[{item['status']}] {tid} {name}", flush=True)
        return item["status"] == "PASS"

    def finish(self):
        required = [x for x in self.doc["results"] if x["required"]]
        passed = bool(required) and all(x["status"] == "PASS" for x in required)
        self.doc["finished_at"] = utcnow()
        self.doc["counts"] = {s: sum(x["status"] == s for x in self.doc["results"]) for s in ("PASS", "FAIL", "UNRUN")}
        self.doc["capability_gate"] = {"passed": passed, "blocking_ids": [x["id"] for x in required if x["status"] != "PASS"]}
        self.doc["baseline_remaining_gates"] = [
            "frozen configuration and complete candidate denominator",
            "candidate-specific holding-state/EOA semantics and missingness handling",
            "cost convention, pilot quality and unchanged canonical block hashes",
        ]
        return 0 if passed else (1 if any(x["status"] == "FAIL" for x in required) else 2)


def require(value, message):
    if not value:
        raise AssertionError(message)


def probe_overrides():
    return {WALLET: {"code": RUNTIMES["Probe"], "balance": hex(10**20), "state": {}},
            CALLER: {"balance": hex(10**20)}}


def probe_call(rpc, token, router, block, timestamp, amount, *, selling=False, overrides=None, approve=True):
    ov = probe_overrides()
    if overrides:
        ov.update(overrides)
    sig = "sell(address,address,uint256,uint256,bool)" if selling else "buy(address,address,uint256,uint256)"
    args = (token, router, amount, timestamp + 3600) + ((approve,) if selling else ())
    result = parse_probe(rpc.call(WALLET, calldata(sig, *args), block, ov))
    result["classification"] = classify_probe(result)
    return result


class Verifier:
    def __init__(self, rpc, args):
        self.rpc, self.args = rpc, args
        self.blocks, self.ctx, self.footprint = {}, {}, {}

    def block(self, value, refresh=False):
        if value in self.blocks and not refresh:
            return self.blocks[value]
        raw = self.rpc.request("eth_getBlockByNumber", [hex(value) if isinstance(value, int) else value, False])
        if not isinstance(raw, dict):
            raise ValueError("Invalid block result")
        b = {"number": quantity(raw["number"]), "timestamp": quantity(raw["timestamp"]), "hash": raw["hash"]}
        require(len(raw_hex(b["hash"])) == 32, "Malformed block hash")
        if isinstance(value, int):
            require(b["number"] == value, "RPC returned a different block")
        self.blocks[value] = b
        self.footprint[b["number"]] = b
        return b

    def at_or_after(self, timestamp):
        head = self.ctx["snapshot"]["number"]
        if timestamp > self.block(head)["timestamp"]:
            raise Unrun("Requested timestamp is beyond the finalized snapshot")
        if timestamp <= self.block(0)["timestamp"]:
            return 0
        return first_true(0, head, lambda n: self.block(n)["timestamp"] >= timestamp)

    def uint(self, target, signature, block, *values):
        self.block(block)
        return word(self.rpc.call(target, calldata(signature, *values), block))

    def need(self, *keys):
        if any(k not in self.ctx for k in keys):
            raise Unrun("Prerequisite not established: " + ",".join(keys))

    def endpoint(self):
        require(quantity(self.rpc.request("eth_chainId", [])) == 1, "Endpoint is not Ethereum mainnet")
        head = self.block("finalized")
        self.ctx["snapshot"] = head
        require(head["number"] > 0, "Invalid finalized head")
        return {"chain_id": 1, "snapshot": head, "evidence": "endpoint_test"}

    def registry(self):
        self.need("snapshot")
        start, end = parse_time(self.args.window_start), parse_time(self.args.window_end)
        require(start < end, "Window start must precede exclusive end")
        b0, b1 = self.at_or_after(start), self.at_or_after(end) - 1
        require(0 < b0 <= b1, "Window contains no usable blocks")
        before = self.uint(FACTORY, "allPairsLength()", b0 - 1)
        after = self.uint(FACTORY, "allPairsLength()", b1)
        require(after >= before, "Factory cumulative count decreased")
        self.ctx.update(window_start=b0, window_end=b1, count_before=before, count_after=after)
        examples = []
        for i in sorted({before, after - 1}) if after > before else []:
            pair = addr_from_word(self.rpc.call(FACTORY, calldata("allPairs(uint256)", i), b1))
            require(pair != ZERO, "Zero pair address")
            t0 = addr_from_word(self.rpc.call(pair, calldata("token0()"), b1))
            t1 = addr_from_word(self.rpc.call(pair, calldata("token1()"), b1))
            require(0 < int(t0, 16) < int(t1, 16), "Invalid canonical token ordering")
            mapped = addr_from_word(self.rpc.call(FACTORY, calldata("getPair(address,address)", t0, t1), b1))
            require(mapped == pair, "Factory index and getPair disagree")
            examples.append({"index": i, "pair": pair, "token0": t0, "token1": t1, "weth_pair": WETH in (t0, t1)})
        self.ctx["registry_ok"] = True
        return {"before_block": self.block(b0-1), "end_block": self.block(b1), "index_range": [before, after],
                "new_pairs_all_assets": after-before, "weth_candidate_N": None,
                "sampled_registry_entries": examples, "full_enumeration_performed": False,
                "boundary_semantics": "[start timestamp, end timestamp); indices [count_before,count_after)"}

    def first_mint(self):
        self.need("registry_ok")
        b = self.ctx["window_end"]
        token = self.args.token
        pair = addr_from_word(self.rpc.call(FACTORY, calldata("getPair(address,address)", token, WETH), b))
        if pair == ZERO:
            raise Unrun("Control token has no V2/WETH pair at the historical probe block")
        cache = {}
        def positive(n):
            if n in cache:
                return cache[n]
            self.block(n)
            result = self.rpc.call(pair, calldata("totalSupply()"), n)
            if result == "0x":
                code = self.rpc.request("eth_getCode", [pair, hex(n)])
                require(code == "0x", "Empty ABI response from an existing pair")
                flag = False  # absence established separately; never parse 0x as zero
            else:
                flag = word(result) > 0
            cache[n] = flag
            return flag
        if not positive(b):
            raise Unrun("Control pair has no first Mint by the probe block")
        mint = first_true(0, b, positive)
        logs = self.rpc.request("eth_getLogs", [{"address": pair, "fromBlock": hex(mint), "toBlock": hex(mint),
                                                "topics": ["0x" + TOPICS["Mint(address,uint256,uint256)"]]}])
        require(isinstance(logs, list) and logs, "Missing one-block Mint cross-check")
        positions = []
        for row in logs:
            require(address(row["address"]) == pair and quantity(row["blockNumber"]) == mint, "Log outside requested pair/block")
            require(row.get("removed") is False, "Removed or unverifiable log")
            require(row["blockHash"].lower() == self.block(mint)["hash"].lower(), "Log block hash mismatch")
            require(len(row["topics"]) == 2 and row["topics"][0].lower() == "0x" + TOPICS["Mint(address,uint256,uint256)"], "Invalid Mint topics")
            require(words(row["data"], 2)[0] > 0 and words(row["data"], 2)[1] > 0, "Invalid first Mint amounts")
            positions.append([quantity(row["transactionIndex"]), quantity(row["logIndex"])])
        # A normal control should predate the candidate cohort, avoiding outcome use.
        require(mint < self.ctx["window_start"], "Choose a pre-window control token; pilot outcomes must not train on the cohort")
        self.ctx.update(pair=pair, mint_block=mint)
        return {"pair": pair, "first_mint": self.block(mint), "first_log_position": min(positions),
                "previous_supply_positive": positive(mint-1), "mint_supply_positive": positive(mint),
                "event_topic": "0x" + TOPICS["Mint(address,uint256,uint256)"], "evidence": "historical_state_and_event"}

    def override(self):
        self.need("registry_ok")
        b = self.ctx["window_end"]
        exit_b = self.at_or_after(self.block(b)["timestamp"] + 30*DAY)
        self.ctx["exit_block"] = exit_b
        details = []
        for block in (b, exit_b):
            # Check virtual identities before injecting code, not a user's address.
            originals = {}
            for who in (WALLET, CALLER, CONTROL_TOKEN, CONTROL_ROUTER):
                require(self.rpc.request("eth_getCode", [who, hex(block)]) == "0x", "Virtual address already has code")
                originals[who] = self.rpc.request("eth_getBalance", [who, hex(block)])
                quantity(originals[who])
            for amount, marker in ((1234567, 7654321), (2345678, 8765432)):
                ov = probe_overrides()
                ov[WALLET] = {"code": RUNTIMES["Probe"], "balance": hex(amount), "stateDiff": {"0x"+pad(0): "0x"+pad(marker)}}
                got = words(self.rpc.call(WALLET, calldata("inspect()"), block, ov), 2)
                require(got == [amount, marker], "Overrides were ignored or misapplied")
                details.append({"block": block, "expected": [amount, marker], "actual": got})
            require(self.rpc.request("eth_getCode", [WALLET, hex(block)]) == "0x", "Injected code persisted")
            require(self.rpc.request("eth_getBalance", [WALLET, hex(block)]) == originals[WALLET], "Injected balance persisted")
        self.ctx["overrides_ok"] = True
        return {"observations": details, "verified": "code + balance + stateDiff applied at two historical blocks; ephemeral"}

    def buy(self):
        self.need("pair", "overrides_ok")
        b, token = self.ctx["window_end"], self.args.token
        identities = {}
        for name, target in (("factory", FACTORY), ("router", ROUTER), ("token", token), ("pair", self.ctx["pair"]), ("weth", WETH)):
            code = raw_hex(self.rpc.request("eth_getCode", [target, hex(b)]))
            require(bool(code), f"Missing {name} code at probe block")
            identities[name] = {"address": target, "code_keccak256": "0x"+keccak(code).hex()}
        pair_factory = addr_from_word(self.rpc.call(self.ctx["pair"], calldata("factory()"), b))
        require(pair_factory == FACTORY, "Pair factory identity mismatch")
        require(addr_from_word(self.rpc.call(ROUTER, calldata("factory()"), b)) == FACTORY, "Router factory mismatch")
        require(addr_from_word(self.rpc.call(ROUTER, calldata("WETH()"), b)) == WETH, "Router WETH mismatch")
        result = probe_call(self.rpc, token, ROUTER, b, self.block(b)["timestamp"], AMOUNT)
        require(result["stage"] == 0, f"Normal control buy did not succeed: {result}")
        received = result["token_after"] - result["token_before"]
        require(result["token_before"] == 0 and received > 0, "Control wallet must start empty and receive tokens")
        require(result["eth_before"] - result["eth_after"] == AMOUNT, "Unexpected native cash debit")
        self.ctx.update(buy_received=received, code_identities=identities)
        return {"block": self.block(b), "input_wei": AMOUNT, "received_token_units": received, "snapshot": result,
                "identities": identities, "wallet_kind": "injected contract; not EOA equivalence"}

    def find_balance_slot(self, token, block):
        data = calldata("balanceOf(address)", WALLET)
        original = word(self.rpc.call(token, data, block))
        sentinels = [1234567890123456789, 2345678901234567890]
        if original in sentinels:
            sentinels = [x + 7 for x in sentinels]
        hits = []
        # Failed calls abort the scan; transport failure is not a slot mismatch.
        for slot in range(self.args.slot_limit):
            key = mapping_key(WALLET, slot)
            first = word(self.rpc.call(token, data, block, {token: {"stateDiff": {key: "0x"+pad(sentinels[0])}}}))
            if first != sentinels[0]:
                continue
            second = word(self.rpc.call(token, data, block, {token: {"stateDiff": {key: "0x"+pad(sentinels[1])}}}))
            if second == sentinels[1]:
                hits.append((slot, key))
        require(word(self.rpc.call(token, data, block)) == original, "Slot probe changed persistent balance")
        if len(hits) != 1:
            raise Unrun(f"Balance mapping unresolved/ambiguous in bounded scan: {len(hits)} hits; not a sellability finding")
        return hits[0]

    def sell(self):
        self.need("buy_received", "exit_block")
        b, token, amount = self.ctx["exit_block"], self.args.token, self.ctx["buy_received"]
        slot, key = self.find_balance_slot(token, b)
        ov = {token: {"stateDiff": {key: "0x"+pad(amount)}}}
        result = probe_call(self.rpc, token, ROUTER, b, self.block(b)["timestamp"], amount, selling=True, overrides=ov)
        require(result["stage"] == 0, f"Normal control exit failed: {result}")
        require(result["token_before"] == amount and result["token_after"] == 0, "Unexpected token debit/residual")
        cash = result["eth_after"] - result["eth_before"]
        require(cash > 0, "No positive native cash credit")
        return {"block": self.block(b), "balance_slot": slot, "balance_storage_key": key, "input_token_units": amount,
                "received_wei_before_gas": cash, "snapshot": result,
                "scope": "separate-state capability probe; actual approve(0), approve(amount) in simulation; not reconstructed holding history",
                "return_multiple": None}

    def controls(self):
        self.need("overrides_ok")
        b = self.ctx["window_end"]
        return run_controls(self.rpc, b, self.block(b)["timestamp"])

    def stable(self):
        self.need("snapshot")
        old = dict(self.footprint)
        self.ctx["original_block_footprint"] = list(old.values())
        for n, b in old.items():
            require(self.block(n, refresh=True)["hash"] == b["hash"], f"Canonical block hash changed at {n}")
        return {"checked_blocks": len(old), "hashes_unchanged": True}


def run_controls(rpc, block, timestamp):
    results = {}
    for kind in ("normal", "tax", "missing_balance", "missing_allowance", "restriction"):
        amount = 10000
        token_state = {"0x"+pad(2): "0x"+pad(1000 if kind == "tax" else 0),
                       "0x"+pad(3): "0x"+pad(1 if kind == "restriction" else 0)}
        ov = {CONTROL_TOKEN: {"code": RUNTIMES["FixtureToken"], "state": token_state},
              CONTROL_ROUTER: {"code": RUNTIMES["FixtureRouter"], "balance": hex(10**20), "state": {}}}
        buy = probe_call(rpc, CONTROL_TOKEN, CONTROL_ROUTER, block, timestamp, amount, overrides=ov)
        expected_tokens = 90000 if kind == "tax" else 100000
        require(buy["stage"] == 0 and buy["token_after"]-buy["token_before"] == expected_tokens, f"{kind}: wrong buy credit")
        token_state[mapping_key(WALLET, 0)] = "0x"+pad(0 if kind == "missing_balance" else expected_tokens)
        sell = probe_call(rpc, CONTROL_TOKEN, CONTROL_ROUTER, block, timestamp, expected_tokens,
                          selling=True, overrides=ov, approve=kind != "missing_allowance")
        expected_stage = {"missing_balance": 10, "missing_allowance": 11, "restriction": 20}.get(kind, 0)
        require(sell["stage"] == expected_stage, f"{kind}: wrong failure stage")
        if expected_stage == 0:
            require(sell["eth_after"]-sell["eth_before"] == (8100 if kind == "tax" else 10000), f"{kind}: wrong sell credit")
            require(sell["token_after"] == 0, f"{kind}: unexpected remaining tokens")
        else:
            require(sell["eth_after"] == sell["eth_before"] and sell["token_after"] == sell["token_before"], f"{kind}: failed sale changed balances")
        if kind == "restriction":
            require(sell["reason"] == "0x"+selector("SellRestricted()"), "Controlled restriction reason mismatch")
            # This annotation is valid ONLY because we defined the artificial rule.
            sell["controlled_cause"] = "fixture_sell_restriction"
        results[kind] = {"buy": buy, "sell": sell}
    return {"artificial_controls": results, "market_honeypot_validation": False,
            "boundary": "passing controls verifies this instrument; arbitrary token semantics remain unverified"}


class LocalEVM:
    """Independent py-evm execution backend for embedded contracts; no network."""
    def call(self, to, data, block, overrides=None):
        from eth_tester import PyEVMBackend
        from eth.vm.message import Message
        from eth.vm.transaction_context import BaseTransactionContext
        backend = PyEVMBackend()
        state = backend.chain.get_vm().state
        for who, change in (overrides or {}).items():
            who_bytes = bytes.fromhex(who[2:])
            if "code" in change:
                state.set_code(who_bytes, raw_hex(change["code"]))
            if "balance" in change:
                state.set_balance(who_bytes, quantity(change["balance"]))
            for key, value in change.get("state", change.get("stateDiff", {})).items():
                state.set_storage(who_bytes, int(key, 16), int(value, 16))
        to_bytes, caller = bytes.fromhex(to[2:]), bytes.fromhex(CALLER[2:])
        msg = Message(gas=8_000_000, to=to_bytes, sender=caller, value=0, data=raw_hex(data),
                      code=state.get_code(to_bytes), should_transfer_value=False)
        ctx = BaseTransactionContext(gas_price=0, origin=caller)
        result = state.computation_class.apply_message(state, msg, ctx)
        if result.is_error:
            raise RuntimeError(f"Local EVM reverted: {result.output.hex()} ({type(result.error).__name__})")
        return "0x"+result.output.hex()


class HistoricalFixtureRPC:
    """Artificial headers/registry + independently executed EVM; NEVER mainnet data."""
    CONTROL_PAIR = "0x000000000000000000000000000000000000f001"
    NEW_PAIR = "0x000000000000000000000000000000000000f002"
    NEW_TOKEN = "0x000000000000000000000000000000000000f003"

    def request(self, method, params):
        if method == "eth_chainId":
            return "0x1"
        if method == "eth_getBlockByNumber":
            n = 300000 if params[0] == "finalized" else int(params[0], 16)
            return {"number": hex(n), "timestamp": hex(n*12), "hash": "0x"+pad(n+1)}
        if method == "eth_getCode":
            target, n = params[0], int(params[1], 16)
            if target in (WALLET,CALLER,CONTROL_TOKEN,CONTROL_ROUTER) or (target == self.CONTROL_PAIR and n<8):
                return "0x"
            return "0x6000"
        if method == "eth_getBalance":
            return "0x0"
        if method == "eth_getLogs":
            f=params[0]
            require(f["fromBlock"]==f["toBlock"]==hex(10), "Fixture requires a one-block Mint query")
            return [{"address":self.CONTROL_PAIR,"blockNumber":hex(10),"blockHash":"0x"+pad(11),
                     "transactionIndex":"0x2","logIndex":"0x3","removed":False,
                     "topics":["0x"+TOPICS["Mint(address,uint256,uint256)"],"0x"+pad(CALLER)],
                     "data":"0x"+pad(10000)+pad(10000)}]
        raise AssertionError("Unexpected fixture request: "+method)

    def call(self, to, data, block, overrides=None):
        sig=data[2:10]
        if to==FACTORY:
            if sig==selector("allPairsLength()"):
                return "0x"+pad(1 if block<20 else 2)
            if sig==selector("allPairs(uint256)"):
                i=word("0x"+data[10:])
                return "0x"+pad(self.CONTROL_PAIR if i==0 else self.NEW_PAIR)
            if sig==selector("getPair(address,address)"):
                t=addr_from_word("0x"+data[10:74])
                return "0x"+pad(self.CONTROL_PAIR if t==DAI else self.NEW_PAIR)
        if to in (self.CONTROL_PAIR,self.NEW_PAIR):
            if sig==selector("totalSupply()"):
                return "0x" if block<8 else "0x"+pad(0 if block<10 else 1000)
            if sig==selector("factory()"):
                return "0x"+pad(FACTORY)
            if sig==selector("token0()"):
                return "0x"+pad(DAI if to==self.CONTROL_PAIR else self.NEW_TOKEN)
            if sig==selector("token1()"):
                return "0x"+pad(WETH)
        if to==ROUTER and sig in (selector("factory()"),selector("WETH()")):
            return "0x"+pad(FACTORY if sig==selector("factory()") else WETH)
        ov={DAI:{"code":RUNTIMES["FixtureToken"],"state":{}},
            ROUTER:{"code":RUNTIMES["FixtureRouter"],"balance":hex(10**20),"state":{}}}
        for target,changes in (overrides or {}).items():
            old=dict(ov.get(target,{}))
            # Base fixture state is empty. stateDiff applies on this base.
            if "stateDiff" in changes:
                old.pop("state",None)
            old.update(changes)
            ov[target]=old
        return LocalEVM().call(to,data,block,ov)


def workflow_selftest():
    try:
        import eth_tester  # noqa: F401
    except ImportError:
        raise Unrun("Install eth-tester and py-evm for the local workflow test")
    args=argparse.Namespace(token=DAI,window_start="1970-01-01T00:03:00Z",
                            window_end="1970-01-01T00:07:00Z",slot_limit=4)
    v=Verifier(HistoricalFixtureRPC(),args)
    results={}
    for name in ("endpoint","registry","first_mint","override","buy","sell","controls","stable"):
        results[name]=getattr(v,name)()
    require(v.ctx["window_start"]==15 and v.ctx["window_end"]==34,"Half-open window off-by-one")
    require(v.ctx["mint_block"]==10,"Old control first Mint mislocated")
    require(results["registry"]["index_range"]==[1,2],"Registry range off-by-one")
    require(results["registry"]["weth_candidate_N"] is None,"Probe falsely claimed full N")
    require(results["sell"]["received_wei_before_gas"]==AMOUNT,"Historical orchestration lost received quantity")
    require(results["sell"]["return_multiple"] is None,"Capability probe became a strategy return")
    # A node accepting but ignoring overrides must fail the observable assertion.
    class IgnoredOverrides(HistoricalFixtureRPC):
        def call(self,to,data,block,overrides=None):
            if to==WALLET and data==calldata("inspect()"):
                return "0x"+pad(0)+pad(0)
            return super().call(to,data,block,overrides)
    bad=Verifier(IgnoredOverrides(),args);bad.endpoint();bad.registry()
    try:
        bad.override()
    except AssertionError:
        pass
    else:
        raise AssertionError("Ignored overrides passed")
    return {"fixture_only":True,"stages":list(results),"first_mint_block":10,
            "window_blocks":[15,34],"ignored_overrides_rejected":True}


def selftest(report):
    def constants():
        for value in (FACTORY, ROUTER, WETH, DAI, WALLET, CALLER, CONTROL_TOKEN, CONTROL_ROUTER):
            require(address(value) == value, "Invalid embedded address")
        require(len({WALLET, CALLER, CONTROL_TOKEN, CONTROL_ROUTER}) == 4, "Virtual addresses collide")
        return {"addresses": 8, "virtual_identities": 4}
    report.check("S.constants", "Deployment and virtual address encoding", constants)
    for signature, expected in SELECTORS.items():
        report.check("S.selector."+expected, signature, lambda s=signature, e=expected: require(selector(s) == e, "Selector mismatch"))
    for signature, expected in TOPICS.items():
        report.check("S.topic."+expected[:8], signature, lambda s=signature, e=expected: require(keccak(s.encode()).hex() == e, "Topic mismatch"))
    report.check("S.keccak", "Independent Keccak vectors", lambda: (
        require(keccak(bytes(64)).hex() == "ad3228b676f7d3cd4284a5443f17f1962b36e491b30a40b2405849e597ba5fb5", "Mapping hash mismatch"),
        require(keccak(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", "Empty hash mismatch")))
    def encoding():
        require(pad("0x1") == "0"*63+"1", "pad failed")
        require(word("0x"+pad(5)) == 5, "word failed")
        require(addr_from_word("0x"+pad(WETH)) == WETH, "address failed")
        bad = [(pad, -1), (pad, 2**256), (word, "0x"), (word, "0x01"), (word, "0x"+"00"*64),
               (addr_from_word, "0x"+pad(2**160)), (address, "0x1"), (quantity, "0x00"), (raw_hex, "0x1")]
        for f, v in bad:
            try:
                f(v)
            except ValueError:
                continue
            raise AssertionError(f"Malformed input accepted: {f.__name__}")
        return {"negative_cases": len(bad)}
    report.check("S.abi", "Strict ABI/hex rejects empty and malformed data", encoding)
    def envelope():
        require(validate_envelope({"jsonrpc":"2.0","id":1,"result":"0x"},1) == "0x", "Envelope rejected")
        for obj in ({}, {"jsonrpc":"2.0","id":2,"result":"0x"}, {"jsonrpc":"2.0","id":1,"result":None},
                    {"jsonrpc":"2.0","id":1,"result":"0x","error":{}}, {"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"revert"}}):
            try:
                validate_envelope(obj,1)
            except RpcFailure:
                continue
            raise AssertionError("Bad RPC response became success")
    report.check("S.rpc", "Null, errors and mismatched IDs cannot pass", envelope)
    def search():
        for threshold in (1,2,3,7,19,20):
            require(first_true(0,20,lambda n,t=threshold:n>=t) == threshold, "Binary boundary error")
        for pred in (lambda n:True, lambda n:False):
            try:
                first_true(0,20,pred)
            except ValueError:
                continue
            raise AssertionError("Unbracketed search accepted")
        timestamps=[0,12,24,48,60]
        require(first_true(0,4,lambda n:timestamps[n]>=25)==3, "Missed-slot timestamp handling failed")
    report.check("S.search", "First Mint and timestamp boundary cases", search)
    def gate():
        r=Report("test");r.doc["results"]=[{"id":"x","status":"UNRUN","required":True}]
        require(r.finish()!=0 and not r.doc["capability_gate"]["passed"], "UNRUN opened gate")
        r.doc["results"]=[{"id":"x","status":"FAIL","required":True}]
        require(r.finish()!=0, "FAIL returned success")
        require(classify_probe({"stage":20})=="execution_reverted_unknown", "Generic revert mislabeled")
        client=RPC("https://rpc.example/v2/very-secret-test-key")
        require("very-secret-test-key" not in client.redact("failed https://rpc.example/v2/very-secret-test-key"), "URL secret leaked")
        try:
            client.request("eth_sendRawTransaction",[])
        except RpcFailure as e:
            require(e.kind=="forbidden_method", "Read-only gate misclassified")
        else:
            raise AssertionError("Transaction method was allowed")
    report.check("S.gates", "Exit status, unknown classification, redaction and read-only guard", gate)
    def evm():
        try:
            import eth_tester  # noqa: F401
        except ImportError:
            raise Unrun("Install eth-tester and py-evm for independent local EVM controls")
        result=run_controls(LocalEVM(),1,1)
        ov=probe_overrides()
        ov[WALLET]["state"]={"0x"+pad(0):"0x"+pad(42)}
        require(words(LocalEVM().call(WALLET,calldata("inspect()"),1,ov),2)==[10**20,42], "Inspector mismatch")
        return result
    report.check("S.evm", "Independent EVM: normal/tax/missing balance/missing allowance/restriction", evm)
    report.check("S.workflow", "Artificial historical workflow and ignored-override rejection", workflow_selftest)
    report.doc["evidence_level"]="offline_functions_and_local_evm; no external RPC run"


def save_report(path, doc):
    path=Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temp.replace(path)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("selftest","run"))
    parser.add_argument("--rpc", help="Prefer local ETH_RPC_URL to avoid URL exposure in shell history")
    parser.add_argument("--rpc-env", default="ETH_RPC_URL")
    parser.add_argument("--token", default=DAI, type=address)
    parser.add_argument("--window-start", default="2026-01-01T00:00:00Z")
    parser.add_argument("--window-end", default="2026-04-01T00:00:00Z", help="Exclusive end")
    parser.add_argument("--max-calls", type=int, default=700)
    parser.add_argument("--max-seconds", type=float, default=600)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--rps", type=float, default=3)
    parser.add_argument("--slot-limit", type=int, default=32)
    parser.add_argument("--out", default="verification_log.json")
    args=parser.parse_args(argv)
    report=Report(args.mode)
    report.doc["script_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report.doc["embedded_source_sha256"]=hashlib.sha256(SOLIDITY_SOURCE.encode()).hexdigest()
    report.doc["embedded_runtime_sha256"]={k:hashlib.sha256(raw_hex(v)).hexdigest() for k,v in RUNTIMES.items()}
    client=None
    try:
        require(args.max_calls>0 and args.max_seconds>0 and args.timeout>0 and 0<args.rps<=100 and 1<=args.slot_limit<=256,"Invalid resource limit")
        if args.mode=="selftest":
            selftest(report)
        else:
            url=args.rpc or os.environ.get(args.rpc_env)
            checks=[("T1","Chain and finalized snapshot","endpoint"),("T2","Actual cohort-window historical registry","registry"),
                    ("T3","First Mint with one-block event cross-check","first_mint"),("T4","Observable historical overrides and isolation","override"),
                    ("T5.buy","Actual token balance delta in one execution","buy"),("T5.sell","Actual exit cash delta with reconstructed balance","sell"),
                    ("T6","Controlled taxes and environment/restriction failures","controls"),("T7","Historical block hash consistency","stable")]
            if not url:
                for tid,name,_ in checks:
                    report.check(tid,name,lambda: (_ for _ in ()).throw(Unrun("No RPC endpoint supplied; not a passed check")))
            else:
                client=RPC(url,max_calls=args.max_calls,max_seconds=args.max_seconds,timeout=args.timeout,rps=args.rps)
                report.doc["rpc_host"]=client.host
                report.doc["probe_parameters"]={"token":args.token,"wallet":WALLET,"caller":CALLER,"input_wei":AMOUNT,
                    "window_start":args.window_start,"window_end_exclusive":args.window_end,"max_calls":args.max_calls,
                    "max_seconds":args.max_seconds,"slot_limit":args.slot_limit}
                v=Verifier(client,args)
                for tid,name,method in checks:
                    report.check(tid,name,getattr(v,method))
                report.doc["block_footprint"]=v.ctx.get("original_block_footprint", list(v.footprint.values()))
                report.doc["rpc_calls"]=client.records
                report.doc["evidence_level"]="endpoint_test_for_recorded_cases_only"
    except (Exception, KeyboardInterrupt) as exc:
        report.doc["results"].append({"id":"FATAL","name":"Run interrupted or initialization failed","status":"FAIL","required":True,
                                      "detail":{"error_type":type(exc).__name__,"message":str(exc)}})
    finally:
        if client:
            report.doc["rpc_calls"]=client.records
            report.doc=client.redact(report.doc)
        code=report.finish()
        save_report(args.out,report.doc)
    print(json.dumps({"counts":report.doc["counts"],"capability_gate":report.doc["capability_gate"],"baseline_ready":False,"log":args.out},ensure_ascii=False))
    return code


if __name__=="__main__":
    sys.exit(main())
