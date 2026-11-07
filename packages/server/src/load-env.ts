import 'reflect-metadata';
import { resolve } from 'node:path';
import { config } from 'dotenv';

// One .env at the repository root, shared by every package.
config({ path: resolve(__dirname, '../../../.env'), quiet: true });
