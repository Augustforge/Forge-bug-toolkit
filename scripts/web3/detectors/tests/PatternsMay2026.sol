// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// Synthetic test contracts containing each May 2026 attack pattern.
// Used by test_detectors.sh to verify new Slither detectors actually fire.

interface IERC20 {
    function transferFrom(address, address, uint256) external returns (bool);
}

// ─── Pattern 1: Ekubo + Cork hook callback without caller validation ─────────────
contract HookCallbackVuln {
    IERC20 public token;

    // VULN: anyone can call this — should require msg.sender == poolManager
    function paymentCallback(address payer, uint256 amount) external {
        token.transferFrom(payer, address(this), amount);
    }

    // VULN: Uniswap v4-style hook without onlyPoolManager
    function beforeSwap(address payer, uint256 amount) external {
        token.transferFrom(payer, msg.sender, amount);
    }
}

// ─── Pattern 2: USPD CPIMP — proxy without atomic init ───────────────────────────
contract Initializable {
    bool internal _initialized;
}

contract VulnProxy is Initializable {
    address public owner;

    // VULN: no _disableInitializers in constructor + no deployer guard
    constructor() {}

    function initialize(address _owner) external {
        require(!_initialized, "already init");
        _initialized = true;
        owner = _owner;
    }
}

// ─── Pattern 3: FOOMCASH Groth16 verifier with suspicious setup ─────────────
library Pairing {
    struct G1Point { uint256 X; uint256 Y; }
    struct G2Point { uint256[2] X; uint256[2] Y; }
    function pairingProd4(G1Point memory, G2Point memory, G1Point memory,
                          G2Point memory, G1Point memory, G2Point memory,
                          G1Point memory, G2Point memory)
        internal view returns (bool) { return true; }
}

contract Groth16Verifier {
    struct VerifyingKey {
        Pairing.G1Point alpha1;
        Pairing.G2Point beta2;
        Pairing.G2Point gamma2;
        Pairing.G2Point delta2;
        Pairing.G1Point[] ic;
    }

    function verifyingKey() internal pure returns (VerifyingKey memory vk) {
        vk.alpha1 = Pairing.G1Point(1, 2);
        vk.beta2 = Pairing.G2Point([uint256(3),4], [uint256(5),6]);
        vk.gamma2 = Pairing.G2Point([uint256(7),8], [uint256(9),10]);
        // VULN: delta2 = gamma2 (placeholder — forgeable proofs)
        vk.delta2 = vk.gamma2;
    }

    function verifyProof(uint256[8] memory proof, uint256[1] memory input)
        public view returns (bool)
    {
        VerifyingKey memory vk = verifyingKey();
        return Pairing.pairingProd4(
            vk.alpha1, vk.beta2, vk.alpha1, vk.gamma2,
            vk.alpha1, vk.delta2, vk.alpha1, vk.beta2
        );
    }
}

// ─── Pattern 4: Giddy partial signature scope ────────────────────────────────
contract GiddyVuln {
    bytes32 public DOMAIN_SEPARATOR;

    // VULN: digest covers only `data`, but recipient & amount are unsigned params
    function executeSignedSwap(
        address recipient,
        uint256 amount,
        bytes calldata data,
        bytes calldata signature
    ) external {
        bytes32 digest = keccak256(abi.encode(DOMAIN_SEPARATOR, data));
        address signer = ecrecover(digest, 27, bytes32(0), bytes32(0));
        require(signer != address(0), "bad sig");
        // VULN: recipient + amount can be replaced by attacker
        IERC20(address(this)).transferFrom(msg.sender, recipient, amount);
    }
}

// ─── Pattern 5: Solv ERC-3525 reentrancy ─────────────────────────────────────
interface IERC3525 {
    function transferFromValue(uint256 fromTokenId, uint256 toTokenId, uint256 value) external;
    function doSafeTransferIn(uint256 tokenId, address from, uint256 amount) external;
    function slot(uint256 tokenId) external view returns (uint256);
    function valueOf(uint256 tokenId) external view returns (uint256);
}

contract Erc3525Vault {
    IERC3525 public erc3525;
    mapping(uint256 => uint256) public balanceOfSlot;
    mapping(uint256 => uint256) public totalSupply;

    // VULN: external call to ERC-3525 doSafeTransferIn before state update + no nonReentrant
    function deposit(uint256 tokenId, uint256 amount) external {
        erc3525.doSafeTransferIn(tokenId, msg.sender, amount);
        // mint via ERC-3525 transferFromValue
        erc3525.transferFromValue(tokenId, tokenId + 1, amount);
        // state update AFTER external calls → reenterable through onERC721Received
        balanceOfSlot[erc3525.slot(tokenId)] += amount;
        totalSupply[tokenId] += amount;
    }
}

// ─── Pattern 6: Rhea slippage with shared intermediate tokens ───────────────────
contract RheaVuln {
    struct Step { address tokenIn; address tokenOut; uint256 amountIn; uint256 expectedOut; }

    // VULN: sums step.expectedOut without checking token uniqueness
    function multiSwap(Step[] calldata steps, uint256 minOut) external {
        uint256 totalExpected = 0;
        for (uint256 i = 0; i < steps.length; i++) {
            totalExpected += steps[i].expectedOut;
        }
        require(totalExpected >= minOut, "slippage");
    }
}

// ─── Pattern 7: KelpDAO LayerZero hardcoded requiredDVNCount=1 ───────────────
contract LayerzeroVuln {
    function setupSendConfig(address endpoint, address library_) external {
        // VULN: hardcoded requiredDVNCount=1
        bytes memory ulnConfig = abi.encode(uint64(20), uint8(1), uint8(0), uint8(0));
        // setConfig call:
        (bool ok,) = endpoint.call(
            abi.encodeWithSignature(
                "setConfig(address,uint32,(uint32,bytes)[])",
                library_, uint32(30101), ulnConfig
            )
        );
        require(ok, "setConfig fail");
    }
}

// ─── Pattern 8: TrustedVolumes unprotected role granting ─────────────────────
contract TrustedVolumesVuln {
    mapping(address => bool) public allowedSigner;
    address public owner;

    constructor() { owner = msg.sender; }

    // VULN: no access control — anyone can add themselves as allowed signer
    function addAllowedOrderSigner(address signer) external {
        allowedSigner[signer] = true;
    }

    // If allowedSigner[msg.sender] then drain user approvals
    function executeOrder(address token, address from, uint256 amount) external {
        require(allowedSigner[msg.sender], "not allowed");
        IERC20(token).transferFrom(from, msg.sender, amount);
    }
}
