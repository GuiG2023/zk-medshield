import { CompiledContract } from '@midnight-ntwrk/midnight-js-protocol/compact-js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export {
  Contract,
  ledger,
  pureCircuits,
  type Ledger,
  type ImpureCircuits,
  type PureCircuits,
} from './managed/blood_glucose/contract/index.js';
import { Contract } from './managed/blood_glucose/contract/index.js';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
export const zkConfigPath = path.resolve(currentDir, 'managed', 'blood_glucose');

export interface PrivateState {
  fastingGlucoseValue: bigint;
}

export const witnesses = {
  fastingGlucose: (context: any) => {
    return [context.privateState, context.privateState.fastingGlucoseValue];
  }
};

export const CompiledBloodGlucoseContract = CompiledContract.make(
  'BloodGlucoseContract',
  Contract,
).pipe(
  CompiledContract.withWitnesses(witnesses),
  CompiledContract.withCompiledFileAssets(zkConfigPath),
);
