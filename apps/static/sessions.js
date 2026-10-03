/* ================================================== */
/* Config (simulation, not generation)                */
/* ================================================== */

const CONFIG = {
    /*
     * Population.
     *
     * Only LIVE sessions are counted (everything except
     * TERMINATED), so sessions that linger in the table
     * after termination neither block arrivals nor
     * satisfy "min".
     *
     * initial
     *     How many sessions already exist when the terminal
     *     opens. [from, to] is rolled once per launch.
     *     Persistent sessions count toward it; the rest
     *     are generated "lived-in".
     *
     * min / max
     *     Soft bounds during the simulation. Below min the
     *     arrival chance jumps to refillChance; at max no
     *     one arrives.
     *
     * arrivalChance
     *     Per-tick chance of a new arrival when population
     *     is at min. It scales down linearly towards max.
     *
     * arrivalDelaySec
     *     An arrival is not instant: once decided, it
     *     connects after a random delay.
     *
     * bootTtlLeft
     *     Fraction of full TTL that boot sessions still
     *     have left (so they look already "lived").
     */
    population: {
        initial: [15, 20],
        min: 10,
        max: 25,

        arrivalChance: 0.04,
        refillChance: 0.5,
        arrivalDelaySec: [2, 8],

        bootTtlLeft: [0.2, 1]
    },

    /*
     * Persistent sessions.
     *
     * When a persistent session ends (for any reason),
     * the same slot reconnects after a random pause.
     * A slot may override this with its own respawnDelaySec.
     */
    persistent: {
        respawnDelaySec: [20, 90]
    },

    tickMs: 1000,

    /*
     * Activity
     *
     * ACTIVE session has a chance to receive activity
     * every tick. If no activity happens for idleAfterSec,
     * the session becomes IDLE.
     */
    activityChance: 0.15,
    wakeChance: 0.10,
    idleAfterSec: 15,

    /*
     * Signal
     *
     * Initial signal is NOT configured here: it belongs
     * to the frequency profile (WORLD.signal.profiles).
     */
    signalMin: 0,
    signalMax: 100,

    /*
     * If signal remains completely lost for this long,
     * the session is terminated.
     */
    signalLossAfterSec: 8,

    /*
     * Random remote-side termination.
     *
     * These are intentionally small per-tick probabilities.
     */
    remoteDisconnectChance: 0.0008,
    adminTerminateChance: 0.00015,

    /*
     * How long TERMINATED sessions stay visible.
     */
    terminatedLifetimeSec: 60
};


const STATE = Object.freeze({
    ACTIVE: "ACTIVE",
    IDLE: "IDLE",
    STALE: "STALE",
    ORPHANED: "ORPHANED",
    TERMINATED: "TERMINATED"
});


const TERMINATION_REASON = Object.freeze({
    TTL_EXPIRED: "TTL_EXPIRED",
    REMOTE_DISCONNECT: "REMOTE_DISCONNECT",
    ADMIN_TERMINATED: "ADMIN_TERMINATED",
    SIGNAL_LOST: "SIGNAL_LOST"
});


/* ================================================== */
/* World data                                         */
/* ================================================== */

const WORLD = {

    /* ------------------------------------------------ */
    /* Pools                                            */
    /* ------------------------------------------------ */

    pools: {
        hostTypes: [
            "archive",
            "wks",
            "relay",
            "node",
            "vault",
            "term",
            "srv"
        ],

        hostNames: [
            "lyra",
            "b4",
            "c2",
            "delta",
            "orion",
            "nexus",
            "zero",
            "kestrel"
        ],

        uidPrefixes: [
            "A",
            "K",
            "R",
            "X",
            "N",
            "T"
        ],

        roles: [
            "OPERATOR",
            "ANALYST",
            "TECH",
            "ADMIN",
            "OBSERVER",
            "—"
        ],

        authTypes: [
            "TOKEN",
            "CERT",
            "LEGACY",
            "LOCAL",
            "UNVERIFIED"
        ],

        flags: [
            "watch",
            "elevated",
            "unscheduled"
        ]
    },


    /* ------------------------------------------------ */
    /* Probabilities                                    */
    /* ------------------------------------------------ */

    chances: {
        flag: 0.2,

        /*
         * IMPORTANT:
         *
         * There is deliberately NO noTtl chance here.
         *
         * A normal generated session always gets a TTL.
         * ttl:null must be explicitly supplied by an event,
         * player session, anomaly, etc.
         */

        reuseHardware: 0.15,
        reuseHost: 0.10
    },


    /* ------------------------------------------------ */
    /* Ranges                                           */
    /* ------------------------------------------------ */

    ranges: {
        startedAgoMinutes: [30, 180],

        /*
         * Every normal generated session gets a TTL.
         */
        ttlSeconds: [300, 3600],

        uidNumber: [10, 99]
    },


    /* ------------------------------------------------ */
    /* Frequency                                        */
    /* ------------------------------------------------ */

    frequency: {

        /*
         * Frequency is stored as DDD.DDD MHz.
         */
        ranges: [
            {
                min: 0.003,
                max: 0.030,
                weight: 2
            },

            {
                min: 0.030,
                max: 0.300,
                weight: 3
            },

            {
                min: 0.300,
                max: 3.000,
                weight: 4
            },

            {
                min: 3.000,
                max: 30.000,
                weight: 8
            },

            {
                min: 30.000,
                max: 300.000,
                weight: 55
            },

            {
                min: 300.000,
                max: 999.999,
                weight: 28
            }
        ],

        precision: 0.001
    },


    /* ------------------------------------------------ */
    /* Signal profiles                                  */
    /* ------------------------------------------------ */

    /*
     * Frequency -> signal profile.
     *
     * These are not intended as real RF propagation
     * physics. They are simulation profiles.
     *
     * baseline
     *     Normal signal level for this frequency band.
     *
     * volatility
     *     Maximum local fluctuation per tick.
     *
     * initialMin / initialMax
     *     Allowed initial signal range for a new session.
     *
     * TODO: 0..100 is a TEMPORARY placeholder for every
     * profile. Real ranges are not decided yet.
     */
    signal: {

        profiles: [
            {
                min: 0.003,
                max: 0.030,

                baseline: 72,
                volatility: 4,

                initialMin: 0,
                initialMax: 100
            },

            {
                min: 0.030,
                max: 0.300,

                baseline: 78,
                volatility: 3,

                initialMin: 0,
                initialMax: 100
            },

            {
                min: 0.300,
                max: 3.000,

                baseline: 82,
                volatility: 2,

                initialMin: 0,
                initialMax: 100
            },

            {
                min: 3.000,
                max: 30.000,

                baseline: 76,
                volatility: 4,

                initialMin: 0,
                initialMax: 100
            },

            {
                min: 30.000,
                max: 300.000,

                baseline: 88,
                volatility: 2,

                initialMin: 0,
                initialMax: 100
            },

            {
                min: 300.000,
                max: 999.999,

                baseline: 80,
                volatility: 3,

                initialMin: 0,
                initialMax: 100
            }
        ]
    },


    /* ------------------------------------------------ */
    /* Lifecycle                                        */
    /* ------------------------------------------------ */

    lifecycle: {

        /*
         * State -> TTL.
         *
         * How many seconds of TTL are consumed per
         * simulation second in each state.
         *
         * 1 = normal. 2 = TTL burns twice as fast, etc.
         *
         * TODO: all 1 for now (no difference between
         * states is decided yet). To make STALE burn
         * faster, change only: STALE: 2
         */
        ttlRateByState: {
            ACTIVE: 1,
            IDLE: 1,
            STALE: 2,
            ORPHANED: 1
        }
    },


    /* ------------------------------------------------ */
    /* Spawn profiles                                   */
    /* ------------------------------------------------ */

    /*
     * New sessions can begin in different lifecycle states.
     *
     * Normal:
     *     ordinary active connection.
     *
     * Idle:
     *     connection exists but remote side is currently
     *     inactive.
     *
     * Orphaned:
     *     connection exists but its remote identity cannot
     *     be resolved.
     */
    spawnProfiles: [
        {
            name: "normal",
            weight: 80,
            overrides: {}
        },

        {
            name: "idle",
            weight: 12,

            overrides: {
                state: STATE.IDLE
            }
        },

        {
            name: "orphaned",
            weight: 8,

            overrides: {
                state: STATE.ORPHANED,
                uuid: "—",
                role: "—",
                auth_type: "UNVERIFIED"
            }
        }
    ],


    /* ------------------------------------------------ */
    /* Persistent sessions                              */
    /* ------------------------------------------------ */

    /*
     * A persistent session is a SLOT with a fixed identity.
     *
     * The session itself is simulated like any other one
     * (signal, state, TTL, random disconnects) and may die.
     * When it does, the slot reconnects after a pause as a
     * NEW session: new sid, new started, new TTL, new signal.
     *
     * slot
     *     Unique slot name (internal, never shown).
     *
     * fields
     *     Fields that stay the same on every reconnect.
     *     Anything not listed here is generated anew each
     *     time. Put "hid" here if the slot should be
     *     recognizable as "the same hardware".
     *
     * respawnDelaySec
     *     Optional [min, max] pause before reconnect.
     *     Default: CONFIG.persistent.respawnDelaySec.
     *
     * TODO: PLACEHOLDER slots, replace with real ones.
     */
    persistentSessions: [

        {
            slot: "slot-a",

            fields: {
                host: "node-0",
                frequency: "121.950",
                hid: "0f:a0:00:0c",
                uuid: "—",
                role: "root",
                auth_type: "",
                flags: ["root"]
            }
        },

        {
            slot: "slot-b",

            fields: {
                host: "relay-zero",
                frequency: "007.410",
                hid: "b1:07:3e:55",
                role: "TECH"
            }
        },

        {
            slot: "slot-c",

            fields: {
                host: "term-delta",
                frequency: "433.200",
                hid: "c8:19:d4:02",
                auth_type: "LEGACY"
            },

            respawnDelaySec: [40, 150]
        }
    ]
};


const UNSAFE_KEYS = new Set([
    "__proto__",
    "constructor",
    "prototype"
]);


/* ================================================== */
/* World data loading                                 */
/* ================================================== */

function mergeDeep(target, source) {

    for (const key of Object.keys(source)) {

        if (UNSAFE_KEYS.has(key)) {
            continue;
        }

        const value = source[key];

        if (Array.isArray(value)) {
            target[key] = value.slice();
        }

        else if (
            value &&
            typeof value === "object" &&
            target[key] &&
            typeof target[key] === "object" &&
            !Array.isArray(target[key])
        ) {
            mergeDeep(target[key], value);
        }

        else {
            target[key] = value;
        }
    }

    return target;
}


function loadWorldData(data) {

    if (data && typeof data === "object") {
        mergeDeep(WORLD, data);
    }
}


async function fetchWorldData(url) {

    try {

        const response = await fetch(
            url,
            {
                credentials: "same-origin"
            }
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        loadWorldData(await response.json());

        return true;
    }

    catch (error) {

        console.warn(
            "World data was not loaded, using defaults:",
            error
        );

        return false;
    }
}


/* ================================================== */
/* Events                                             */
/* ================================================== */

const handlers = {
    create: [],
    terminate: [],
    remove: [],
    stateChange: []
};


function on(event, handler) {

    if (!handlers[event]) {
        throw new Error(
            `Unknown event: ${event}`
        );
    }

    handlers[event].push(handler);
}


function emit(event, session) {

    for (const handler of handlers[event]) {

        try {
            handler(session);
        }

        catch (error) {

            console.error(
                `Handler for "${event}" failed:`,
                error
            );
        }
    }
}


/*
 * stateChange handlers receive:
 *
 *     (session, previousState, newState, now)
 */
function emitStateChange(
    session,
    previousState,
    now
) {

    for (const handler of handlers.stateChange) {

        try {

            handler(
                session,
                previousState,
                session.state,
                now
            );
        }

        catch (error) {

            console.error(
                "State change handler failed:",
                error
            );
        }
    }
}


/*
 * The only place where a living session changes state.
 *
 * Entering ACTIVE always counts as fresh activity.
 */
function setState(
    session,
    newState,
    now
) {

    if (session.state === newState) {
        return;
    }

    const previousState =
        session.state;

    session.state =
        newState;

    if (newState === STATE.ACTIVE) {

        session.last_active =
            new Date(now);
    }

    emitStateChange(
        session,
        previousState,
        now
    );
}


/* ================================================== */
/* Random                                             */
/* ================================================== */

function mulberry32(seed) {

    return function () {

        seed |= 0;
        seed =
            (seed + 0x6D2B79F5) |
            0;

        let t =
            Math.imul(
                seed ^ (seed >>> 15),
                1 | seed
            );

        t =
            (
                t +
                Math.imul(
                    t ^ (t >>> 7),
                    61 | t
                )
            ) ^ t;

        return (
            (t ^ (t >>> 14)) >>> 0
        ) / 4294967296;
    };
}


function hashString(str) {

    let h = 2166136261;

    for (let i = 0; i < str.length; i++) {

        h ^= str.charCodeAt(i);

        h =
            Math.imul(
                h,
                16777619
            );
    }

    return h >>> 0;
}


const seedParam =
    new URLSearchParams(
        window.location.search
    ).get("seed");


const random =
    seedParam !== null
        ? mulberry32(
            hashString(seedParam)
        )
        : Math.random;


function chance(p) {
    return random() < p;
}


function randomItem(array) {

    return array[
        Math.floor(
            random() * array.length
        )
    ];
}


function randomInt(min, max) {

    return Math.floor(
        random() * (max - min + 1)
    ) + min;
}


function randomFromRange(range) {

    return randomInt(
        range[0],
        range[1]
    );
}


function pickWeighted(items) {

    const weightOf =
        item =>
            item.weight === undefined
                ? 1
                : item.weight;


    const total =
        items.reduce(
            (sum, item) =>
                sum + weightOf(item),
            0
        );


    let roll =
        random() * total;


    for (const item of items) {

        roll -= weightOf(item);

        if (roll < 0) {
            return item;
        }
    }


    return items[
        items.length - 1
    ];
}


function hex(length) {

    const chars =
        "0123456789abcdef";

    let result = "";

    for (let i = 0; i < length; i++) {
        result += randomItem(chars);
    }

    return result;
}


/* ================================================== */
/* Basic generators                                   */
/* ================================================== */

function randomSid() {

    return `0x${hex(4)}`;
}


function randomHardwareId() {

    return Array
        .from(
            {
                length: 4
            },
            () => hex(2)
        )
        .join(":");
}


function randomUid() {

    return (
        randomItem(
            WORLD.pools.uidPrefixes
        ) +
        randomFromRange(
            WORLD.ranges.uidNumber
        )
    );
}


function randomHost() {

    return (
        randomItem(
            WORLD.pools.hostTypes
        ) +
        "-" +
        randomItem(
            WORLD.pools.hostNames
        )
    );
}


function randomFrequency() {

    const ranges =
        WORLD.frequency.ranges;


    const range =
        pickWeighted(ranges);


    const value =
        range.min +
        random() *
        (range.max - range.min);


    const [
        whole,
        fraction
    ] =
        value
            .toFixed(3)
            .split(".");


    return (
        whole.padStart(3, "0") +
        "." +
        fraction
    );
}


function randomFlags() {

    return WORLD.pools.flags.filter(
        () => chance(WORLD.chances.flag)
    );
}


/*
 * A value that already exists in another session.
 */
function existingValue(ctx, field) {

    const values =
        ctx.manager
            .all()
            .map(
                session =>
                    session[field]
            )
            .filter(
                value =>
                    value &&
                    value !== "???"
            );

    return values.length
        ? randomItem(values)
        : null;
}


/* ================================================== */
/* Signal                                             */
/* ================================================== */

function getSignalProfile(frequency) {

    const value =
        Number(frequency);


    /*
     * Non-numeric frequencies are unknown.
     */
    if (!Number.isFinite(value)) {

        return {
            baseline: 50,
            volatility: 6,

            initialMin: 0,
            initialMax: 100
        };
    }


    for (
        const profile
        of WORLD.signal.profiles
    ) {

        if (
            value >= profile.min &&
            value < profile.max
        ) {
            return profile;
        }
    }


    return WORLD.signal.profiles[
        WORLD.signal.profiles.length - 1
    ];
}


/*
 * Initial signal belongs to the frequency profile.
 */
function randomInitialSignal(
    frequency
) {

    const profile =
        getSignalProfile(
            frequency
        );


    const min =
        Math.max(
            CONFIG.signalMin,
            profile.initialMin
        );


    const max =
        Math.min(
            CONFIG.signalMax,
            profile.initialMax
        );


    /*
     * Misconfigured profile: do not crash.
     */
    if (min > max) {
        return min;
    }


    return randomInt(
        min,
        max
    );
}


/*
 * Signal -> connection.
 *
 * Connection is NEVER generated independently.
 */
function getConnectionState(signal) {

    if (signal >= 70) {
        return "STABLE";
    }

    if (signal >= 40) {
        return "DEGRADED";
    }

    if (signal >= 20) {
        return "UNSTABLE";
    }

    return "LOSS";
}


/*
 * Update signal by one simulation tick.
 *
 * Signal is not replaced with a completely random number.
 * It moves gradually around the normal level of the
 * profile selected by frequency.
 */
function updateSignal(session) {

    if (
        session.state ===
        STATE.ORPHANED
    ) {

        session.signal = 0;
        session.connection = "LOSS";

        return;
    }


    const profile =
        getSignalProfile(
            session.frequency
        );


    /*
     * Pull signal toward profile baseline.
     */
    let drift = 0;

    if (
        session.signal <
        profile.baseline
    ) {
        drift = randomInt(1, 3);
    }

    else if (
        session.signal >
        profile.baseline
    ) {
        drift = -randomInt(1, 3);
    }


    /*
     * Local fluctuation.
     */
    const noise =
        randomInt(
            -profile.volatility,
            profile.volatility
        );


    session.signal +=
        drift + noise;


    session.signal =
        Math.max(
            CONFIG.signalMin,
            Math.min(
                CONFIG.signalMax,
                session.signal
            )
        );


    /*
     * Connection is derived from signal.
     */
    session.connection =
        getConnectionState(
            session.signal
        );
}


/* ================================================== */
/* State resolution                                   */
/* ================================================== */

/*
 * Has signal been completely lost for long enough
 * to terminate the session?
 *
 * ORPHANED sessions never have a signal by definition,
 * so signal loss is not a termination path for them
 * (they are bounded by TTL only).
 */
function isSignalLossSustained(
    session,
    now
) {

    if (
        session.state ===
        STATE.ORPHANED
    ) {
        return false;
    }


    if (
        session.connection !== "LOSS"
    ) {

        session.signalLostSince =
            null;

        return false;
    }


    if (
        !session.signalLostSince
    ) {

        session.signalLostSince =
            new Date(now);

        return false;
    }


    const lostFor =
        (
            now.getTime() -
            session.signalLostSince.getTime()
        ) / 1000;


    return (
        lostFor >=
        CONFIG.signalLossAfterSec
    );
}


/*
 * Connection influences lifecycle state.
 *
 * DEGRADED / UNSTABLE do not automatically mean
 * STALE or TERMINATED.
 *
 * Only sustained LOSS has a termination path.
 */
function resolveStateFromConnection(
    session
) {

    /*
     * ORPHANED is an explicit lifecycle condition.
     */
    if (
        session.state ===
        STATE.ORPHANED
    ) {
        return STATE.ORPHANED;
    }


    /*
     * STALE is an explicit abnormal state.
     *
     * It recovers once connection becomes stable.
     */
    if (
        session.state ===
        STATE.STALE
    ) {

        return (
            session.connection ===
            "STABLE"
        )
            ? STATE.ACTIVE
            : STATE.STALE;
    }


    /*
     * ACTIVE / IDLE are controlled by activity.
     */
    return session.state;
}


/*
 * State -> TTL rate.
 *
 * Actual rates live in WORLD.lifecycle.
 */
function getTTLRate(session) {

    const rate =
        WORLD.lifecycle
            .ttlRateByState[
                session.state
            ];


    /*
     * Unknown state falls back to one second.
     */
    if (
        typeof rate !== "number" ||
        !Number.isFinite(rate)
    ) {
        return 1;
    }


    return Math.max(
        0,
        rate
    );
}


/*
 * Apply state-dependent TTL consumption.
 */
function updateTTL(session) {

    if (
        session.ttl === null ||
        session.ttl <= 0
    ) {
        return;
    }


    session.ttl -=
        getTTLRate(session);


    if (session.ttl < 0) {
        session.ttl = 0;
    }
}


/* ================================================== */
/* Generator registry                                 */
/* ================================================== */

/*
 * Signal and connection are NOT here.
 *
 * Signal depends on frequency, so it is generated in
 * buildSession() after frequency exists. Connection is
 * derived from signal.
 */
const GENERATORS = {

    sid(ctx) {

        let sid;

        do {
            sid = randomSid();
        }
        while (
            ctx.manager.get(sid)
        );

        return sid;
    },


    host(ctx) {

        if (
            chance(
                WORLD.chances.reuseHost
            )
        ) {

            const reused =
                existingValue(
                    ctx,
                    "host"
                );

            if (reused) {
                return reused;
            }
        }

        return randomHost();
    },


    frequency() {

        return randomFrequency();
    },


    uuid() {

        return randomUid();
    },


    role() {

        return randomItem(
            WORLD.pools.roles
        );
    },


    started(ctx) {

        const minutes =
            randomFromRange(
                WORLD.ranges
                    .startedAgoMinutes
            );


        return new Date(
            ctx.now.getTime() -
            minutes * 60 * 1000
        );
    },


    last_active(ctx) {

        const from =
            ctx.session.started
                .getTime();


        const to =
            Math.max(
                from,
                ctx.now.getTime()
            );


        return new Date(
            from +
            random() *
            (to - from)
        );
    },


    state() {

        return STATE.ACTIVE;
    },


    /*
     * Every ordinary generated session
     * receives a TTL.
     *
     * No random null TTL.
     */
    ttl() {

        return randomFromRange(
            WORLD.ranges.ttlSeconds
        );
    },


    hid(ctx) {

        if (
            chance(
                WORLD.chances.reuseHardware
            )
        ) {

            const reused =
                existingValue(
                    ctx,
                    "hid"
                );

            if (reused) {
                return reused;
            }
        }


        return randomHardwareId();
    },


    auth_type() {

        return randomItem(
            WORLD.pools.authTypes
        );
    },


    flags() {

        return randomFlags();
    }
};


/* ================================================== */
/* Formatting                                         */
/* ================================================== */

function formatTime(date) {

    return date.toLocaleTimeString(
        [],
        {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false
        }
    );
}


function formatDateTime(date) {

    return date.toLocaleString(
        [],
        {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false
        }
    );
}


function formatTTL(seconds) {

    if (seconds === null) {
        return "—";
    }


    if (seconds <= 0) {
        return "00:00";
    }


    /*
     * TTL rate may be fractional.
     */
    seconds =
        Math.ceil(seconds);


    const hours =
        Math.floor(
            seconds / 3600
        );


    const minutes =
        Math.floor(
            (seconds % 3600) / 60
        );


    const secs =
        seconds % 60;


    return [
        hours,
        minutes,
        secs
    ]
        .map(
            n =>
                String(n)
                    .padStart(2, "0")
        )
        .join(":");
}


/* ================================================== */
/* Session model                                      */
/* ================================================== */

function buildSession(overrides = {}) {

    const ctx = {

        now: new Date(),

        manager: sessionManager,

        session: {
            ...overrides
        }
    };


    /*
     * Generate ordinary fields.
     *
     * Explicit overrides always win.
     */
    for (
        const [field, generate]
        of Object.entries(GENERATORS)
    ) {

        if (
            field in overrides
        ) {
            continue;
        }


        ctx.session[field] =
            generate(ctx);
    }


    /*
     * Frequency determines the signal profile,
     * the profile determines initial signal.
     *
     * Explicit signal is respected.
     */
    if (
        !("signal" in overrides)
    ) {

        ctx.session.signal =
            randomInitialSignal(
                ctx.session.frequency
            );
    }


    /*
     * ORPHANED has no usable signal.
     */
    if (
        ctx.session.state ===
        STATE.ORPHANED
    ) {

        ctx.session.signal = 0;
        ctx.session.connection = "LOSS";
    }

    else {

        /*
         * Connection is ALWAYS derived from signal,
         * even if an override tried to set it.
         */
        ctx.session.connection =
            getConnectionState(
                ctx.session.signal
            );
    }


    /*
     * Initial signal-loss tracking.
     * (ORPHANED is not tracked: it has no signal by design.)
     */
    ctx.session.signalLostSince =
        (
            ctx.session.state !==
                STATE.ORPHANED &&
            ctx.session.connection ===
                "LOSS"
        )
            ? new Date(ctx.now)
            : null;


    /*
     * A generated ACTIVE session must have been active
     * recently, otherwise it would flip to IDLE on its
     * very first tick.
     */
    if (
        ctx.session.state ===
            STATE.ACTIVE &&
        !("last_active" in overrides)
    ) {

        const agoSec =
            randomInt(
                0,
                Math.max(
                    0,
                    CONFIG.idleAfterSec - 1
                )
            );

        ctx.session.last_active =
            new Date(
                ctx.now.getTime() -
                agoSec * 1000
            );
    }


    /*
     * Runtime fields.
     */
    if (
        !("termination_reason" in ctx.session)
    ) {
        ctx.session.termination_reason =
            null;
    }


    if (
        !("terminated_at" in ctx.session)
    ) {
        ctx.session.terminated_at =
            null;
    }


    /*
     * Persistent slot name (null for ordinary sessions).
     */
    if (
        !("slot" in ctx.session)
    ) {
        ctx.session.slot =
            null;
    }


    return ctx.session;
}


/* ================================================== */
/* Termination                                        */
/* ================================================== */

function terminateSession(
    session,
    reason,
    now
) {

    if (
        session.state ===
        STATE.TERMINATED
    ) {
        return;
    }


    session.state =
        STATE.TERMINATED;


    session.termination_reason =
        reason;


    session.terminated_at =
        new Date(now);


    /*
     * TTL reaching zero is represented
     * as zero rather than null.
     */
    if (
        reason ===
        TERMINATION_REASON.TTL_EXPIRED
    ) {
        session.ttl = 0;
    }


    emit(
        "terminate",
        session
    );
}


/* ================================================== */
/* Lifecycle                                          */
/* ================================================== */

/*
 * Causal chain per tick:
 *
 *   signal -> connection -> state -> TTL -> termination
 */
function tickSession(
    session,
    now
) {

    if (
        session.state ===
        STATE.TERMINATED
    ) {
        return;
    }


    /* ---------------------------------------------- */
    /* Signal (-> connection)                         */
    /* ---------------------------------------------- */

    updateSignal(session);


    /* ---------------------------------------------- */
    /* Sustained signal loss                          */
    /* ---------------------------------------------- */

    if (
        isSignalLossSustained(
            session,
            now
        )
    ) {

        terminateSession(
            session,
            TERMINATION_REASON.SIGNAL_LOST,
            now
        );

        return;
    }


    /* ---------------------------------------------- */
    /* Connection -> State                            */
    /* ---------------------------------------------- */

    setState(
        session,
        resolveStateFromConnection(
            session
        ),
        now
    );


    /* ---------------------------------------------- */
    /* Activity: ACTIVE <-> IDLE                      */
    /* ---------------------------------------------- */

    if (
        session.state ===
        STATE.ACTIVE
    ) {

        /*
         * Remote side produces activity.
         */
        if (
            chance(
                CONFIG.activityChance
            )
        ) {

            session.last_active =
                new Date(now);
        }


        const inactiveFor =
            (
                now.getTime() -
                session.last_active
                    .getTime()
            ) / 1000;


        /*
         * ACTIVE -> IDLE.
         */
        if (
            inactiveFor >=
            CONFIG.idleAfterSec
        ) {

            setState(
                session,
                STATE.IDLE,
                now
            );
        }
    }

    else if (
        session.state ===
        STATE.IDLE
    ) {

        /*
         * IDLE -> ACTIVE: the remote side
         * starts doing something again.
         */
        if (
            chance(
                CONFIG.wakeChance
            )
        ) {

            setState(
                session,
                STATE.ACTIVE,
                now
            );
        }
    }


    /* ---------------------------------------------- */
    /* State -> TTL                                   */
    /* ---------------------------------------------- */

    updateTTL(session);


    if (
        session.ttl !== null &&
        session.ttl <= 0
    ) {

        terminateSession(
            session,
            TERMINATION_REASON.TTL_EXPIRED,
            now
        );

        return;
    }


    /* ---------------------------------------------- */
    /* Remote disconnect                              */
    /* ---------------------------------------------- */

    if (
        chance(
            CONFIG.remoteDisconnectChance
        )
    ) {

        terminateSession(
            session,
            TERMINATION_REASON.REMOTE_DISCONNECT,
            now
        );

        return;
    }


    /* ---------------------------------------------- */
    /* Admin termination                              */
    /* ---------------------------------------------- */

    if (
        chance(
            CONFIG.adminTerminateChance
        )
    ) {

        terminateSession(
            session,
            TERMINATION_REASON.ADMIN_TERMINATED,
            now
        );

        return;
    }
}


/* ================================================== */
/* Session Manager                                    */
/* ================================================== */

class SessionManager {

    constructor() {

        this.sessions =
            new Map();
    }


    add(session) {

        this.sessions.set(
            session.sid,
            session
        );


        emit(
            "create",
            session
        );


        return session;
    }


    get(sid) {

        return this.sessions.get(
            sid
        );
    }


    remove(sid) {

        const session =
            this.sessions.get(sid);


        if (
            this.sessions.delete(sid)
        ) {

            emit(
                "remove",
                session
            );
        }
    }


    all() {

        return Array.from(
            this.sessions.values()
        );
    }


    count() {

        return this.sessions.size;
    }


    /*
     * Sessions that are still alive
     * (TERMINATED ones are not counted).
     */
    liveCount() {

        let n = 0;

        for (
            const session
            of this.sessions.values()
        ) {

            if (
                session.state !==
                STATE.TERMINATED
            ) {
                n++;
            }
        }

        return n;
    }


    tick(
        now = new Date()
    ) {

        /*
         * Array.from allows us to remove
         * sessions while iterating.
         */
        for (
            const session
            of Array.from(
                this.sessions.values()
            )
        ) {

            tickSession(
                session,
                now
            );


            if (
                session.state !==
                STATE.TERMINATED
            ) {
                continue;
            }


            if (
                !session.terminated_at
            ) {

                session.terminated_at =
                    new Date(now);
            }


            const age =
                now.getTime() -
                session.terminated_at
                    .getTime();


            if (
                age >=
                CONFIG.terminatedLifetimeSec *
                1000
            ) {

                this.remove(
                    session.sid
                );
            }
        }
    }
}


const sessionManager =
    new SessionManager();


/* ================================================== */
/* Session creation                                   */
/* ================================================== */

function createSession(
    overrides = {}
) {

    return sessionManager.add(
        buildSession(
            overrides
        )
    );
}


/* ================================================== */
/* DOM                                                */
/* ================================================== */

const tableBody =
    document.getElementById(
        "sessions-body"
    );


const sessionCount =
    document.getElementById(
        "session-count"
    );


/* ================================================== */
/* Session inspector launcher                         */
/* ================================================== */

function openSessionInspector(
    sid
) {

    const session =
        sessionManager.get(sid);


    if (!session) {
        return;
    }


    const desktop =
        window.parent &&
        window.parent.desktopAPI;


    if (
        !desktop ||
        typeof desktop.openApp !==
        "function"
    ) {

        console.error(
            "desktopAPI.openApp() is not available."
        );

        return;
    }


    if (
        typeof window.SESSION_INSPECTOR_BASE !==
        "string"
    ) {

        console.error(
            "SESSION_INSPECTOR_BASE is not defined."
        );

        return;
    }


    desktop.openApp(

        `session-${session.sid}`,

        `sessions.mon/${session.sid}`,

        window.SESSION_INSPECTOR_BASE.replace(
            "__SID__",
            encodeURIComponent(
                session.sid
            )
        )
    );
}


/*
 * One listener for the whole table.
 */
if (tableBody) {

    tableBody.addEventListener(
        "click",
        event => {

            const row =
                event.target.closest(
                    "tr"
                );


            if (
                row &&
                row.dataset.sid
            ) {

                openSessionInspector(
                    row.dataset.sid
                );
            }
        }
    );
}


/* ================================================== */
/* Rendering                                          */
/* ================================================== */

const COLUMNS = [

    s => s.sid,

    s =>
        `${s.host}@${s.frequency}`,

    s => `${s.connection} (${s.signal}%)`,

    s => s.uuid,

    s => s.role,

    s => formatTime(
        s.started
    ),

    s => formatTime(
        s.last_active
    ),

    s => s.state,

    s => formatTTL(
        s.ttl
    )
];


const CONNECTION_COLUMN = 2;
const STATE_COLUMN = 7;


const rowsBySid =
    new Map();


function createRow(sid) {

    const row =
        document.createElement(
            "tr"
        );


    row.dataset.sid =
        sid;


    for (
        let i = 0;
        i < COLUMNS.length;
        i++
    ) {

        row.appendChild(
            document.createElement(
                "td"
            )
        );
    }


    return row;
}


function updateRow(
    row,
    session
) {

    COLUMNS.forEach(
        (getValue, index) => {

            const cell =
                row.children[index];


            const value =
                String(
                    getValue(session)
                );


            /*
             * Only touch the DOM when
             * the displayed value changed.
             */
            if (
                cell.textContent !==
                value
            ) {

                cell.textContent =
                    value;
            }
        }
    );


    /*
     * Connection class.
     */
    row.children[
        CONNECTION_COLUMN
    ].className =
        `connection-${session.connection.toLowerCase()}`;


    /*
     * State class.
     */
    row.children[
        STATE_COLUMN
    ].className =
        `state-${session.state.toLowerCase()}`;
}


function renderSessions() {

    if (!tableBody) {
        return;
    }


    const sessions =
        sessionManager.all();


    const present =
        new Set();


    for (
        const session
        of sessions
    ) {

        present.add(
            session.sid
        );


        let row =
            rowsBySid.get(
                session.sid
            );


        if (!row) {

            row =
                createRow(
                    session.sid
                );


            rowsBySid.set(
                session.sid,
                row
            );


            tableBody.appendChild(
                row
            );
        }


        updateRow(
            row,
            session
        );
    }


    /*
     * Remove rows for sessions that
     * no longer exist.
     */
    for (
        const [sid, row]
        of rowsBySid
    ) {

        if (
            !present.has(sid)
        ) {

            row.remove();

            rowsBySid.delete(
                sid
            );
        }
    }


    if (sessionCount) {

        sessionCount.textContent =
            String(
                sessions.length
            ).padStart(
                2,
                "0"
            );
    }
}


/* ================================================== */
/* Runtime simulation                                 */
/* ================================================== */

function updateSessions() {

    const now =
        new Date();


    sessionManager.tick(now);

    persistentStep(now);

    populationStep(now);

    renderSessions();
}


/*
 * Boot sessions have already lived for a while:
 * part of their TTL is gone.
 */
function ageSession(session) {

    if (
        session.ttl === null
    ) {
        return;
    }


    const [lo, hi] =
        CONFIG.population.bootTtlLeft;


    const fraction =
        lo +
        random() * (hi - lo);


    session.ttl =
        Math.max(
            30,
            Math.round(
                session.ttl * fraction
            )
        );
}


/*
 * Creates one generated session from a weighted
 * spawn profile.
 *
 * boot = true -> the session looks already lived-in.
 */
function spawnRandomSession(
    boot = false
) {

    const profile =
        pickWeighted(
            WORLD.spawnProfiles
        );


    const session =
        buildSession(
            {
                ...(profile.overrides || {})
            }
        );


    if (boot) {
        ageSession(session);
    }


    return sessionManager.add(
        session
    );
}


/* ================================================== */
/* Persistent sessions                                */
/* ================================================== */

/*
 * slot name -> {
 *     def         definition from WORLD.persistentSessions
 *     respawnAt   ms timestamp of the planned reconnect, or null
 *     history     every sid this slot has ever used
 * }
 */
const persistentSlots =
    new Map();


function spawnPersistent(
    slot,
    boot = false
) {

    const session =
        buildSession(
            {
                ...(slot.def.fields || {}),
                slot: slot.def.slot
            }
        );


    if (boot) {
        ageSession(session);
    }


    slot.respawnAt =
        null;


    slot.history.push(
        session.sid
    );


    return sessionManager.add(
        session
    );
}


function initPersistentSessions() {

    /*
     * Whenever a persistent session ends, plan the
     * reconnect of its slot.
     */
    on(
        "terminate",
        session => {

            if (!session.slot) {
                return;
            }


            const slot =
                persistentSlots.get(
                    session.slot
                );


            if (!slot) {
                return;
            }


            const range =
                slot.def.respawnDelaySec ||
                CONFIG.persistent
                    .respawnDelaySec;


            slot.respawnAt =
                session.terminated_at
                    .getTime() +
                randomFromRange(range) *
                1000;
        }
    );


    for (
        const def
        of WORLD.persistentSessions || []
    ) {

        if (
            !def.slot ||
            persistentSlots.has(
                def.slot
            )
        ) {
            continue;
        }


        const slot = {
            def,
            respawnAt: null,
            history: []
        };


        persistentSlots.set(
            def.slot,
            slot
        );


        spawnPersistent(
            slot,
            true
        );
    }
}


/*
 * Reconnect slots whose pause has passed.
 *
 * Persistent sessions count towards min/max like any
 * other live session, but they return regardless of max.
 */
function persistentStep(now) {

    for (
        const slot
        of persistentSlots.values()
    ) {

        if (
            slot.respawnAt !== null &&
            now.getTime() >=
            slot.respawnAt
        ) {

            spawnPersistent(slot);
        }
    }
}


/*
 * The terminal is not empty when it opens:
 * persistent sessions first, then generated ones
 * up to the rolled initial population.
 */
function createBootPopulation() {

    initPersistentSessions();


    const [lo, hi] =
        CONFIG.population.initial;


    const target =
        Math.min(
            randomInt(lo, hi),
            CONFIG.population.max
        );


    while (
        sessionManager.liveCount() <
        target
    ) {

        spawnRandomSession(true);
    }


    renderSessions();
}


/*
 * Time (ms) at which the already-decided arrival
 * connects, or null if nobody is about to arrive.
 */
let nextArrivalAt = null;


/*
 * One tick of population control.
 *
 * live >= max : nobody arrives.
 * live <  min : arrival is very likely.
 * otherwise   : chance falls linearly from
 *               arrivalChance (at min) to 0 (at max).
 *
 * A decided arrival connects after a random delay.
 */
function populationStep(now) {

    const {
        min,
        max,
        arrivalChance,
        refillChance,
        arrivalDelaySec
    } = CONFIG.population;


    const live =
        sessionManager.liveCount();


    if (live >= max) {

        nextArrivalAt = null;

        return;
    }


    if (nextArrivalAt === null) {

        const p =
            live < min
                ? refillChance
                : arrivalChance *
                  (max - live) /
                  Math.max(1, max - min);


        if (chance(p)) {

            nextArrivalAt =
                now.getTime() +
                randomFromRange(
                    arrivalDelaySec
                ) * 1000;
        }

        return;
    }


    if (
        now.getTime() >=
        nextArrivalAt
    ) {

        nextArrivalAt = null;

        spawnRandomSession();
    }
}


/* ================================================== */
/* Manual controls                                    */
/* ================================================== */

function adminTerminateSession(
    sid,
    now = new Date()
) {

    const session =
        sessionManager.get(sid);


    if (!session) {
        return false;
    }


    terminateSession(
        session,
        TERMINATION_REASON.ADMIN_TERMINATED,
        now
    );


    return true;
}


function remoteDisconnectSession(
    sid,
    now = new Date()
) {

    const session =
        sessionManager.get(sid);


    if (!session) {
        return false;
    }


    terminateSession(
        session,
        TERMINATION_REASON.REMOTE_DISCONNECT,
        now
    );


    return true;
}


/* ================================================== */
/* Public API                                         */
/* ================================================== */

window.SessionsAPI = {

    world: WORLD,

    config: CONFIG,

    states: STATE,

    terminationReasons:
        TERMINATION_REASON,

    generators:
        GENERATORS,

    manager:
        sessionManager,

    on,

    loadWorldData,

    fetchWorldData,

    buildSession,

    createSession,

    terminateSession,

    adminTerminateSession,

    remoteDisconnectSession,

    getSignalProfile,

    getConnectionState,

    updateSignal,

    updateTTL,

    resolveStateFromConnection,

    populationStep,

    persistentSlots,

    persistentStep,

    spawnRandomSession,

    renderSessions
};


/* ================================================== */
/* Start                                              */
/* ================================================== */

async function start() {

    /*
     * Optional external world data.
     */
    if (
        typeof window.SESSION_WORLD_URL ===
        "string"
    ) {

        await fetchWorldData(
            window.SESSION_WORLD_URL
        );
    }


    /*
     * The terminal opens with sessions already present.
     */
    createBootPopulation();


    /*
     * Simulation tick (also drives arrivals).
     */
    setInterval(
        updateSessions,
        CONFIG.tickMs
    );
}


start();