/**
 * The one place zod is configured. zod 4 normally probes `new Function("")` to see whether it may
 * compile validators; under a strict Content-Security-Policy the blocked probe is caught, but the
 * browser still reports it as a violation. `jitless` skips the probe (validation is a little slower
 * and no different). Import `z` from here, not from "zod".
 */
import { z } from "zod";

z.config({ jitless: true });

export { z };
