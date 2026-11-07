import { AsyncLocalStorage } from 'node:async_hooks';
import { InternalServerErrorException } from '@nestjs/common';
import type { Kysely, Transaction } from 'kysely';
import { db } from './pool';

/**
 * The repository pattern from Quarry, without principals or RLS: @Transactional opens a transaction and
 * hands the method its handle via `this.trx`. A decorated method called while one is running joins it, so a
 * repository method composes the others and the outermost call commits. Services never see a transaction.
 */
const transactionStorage = new AsyncLocalStorage<Transaction<unknown>>();

/** Base class factory: `this.trx` types against the tables T describes. */
export function Repository<T>() {

    abstract class RepositoryBase {

        /** The transaction @Transactional opened for the current call. */
        protected get trx(): Transaction<T> {
            const trx = transactionStorage.getStore();

            if (!trx)
                throw new InternalServerErrorException('No open transaction — is the method missing @Transactional?');

            return trx as Transaction<T>;
        }
    }

    return RepositoryBase;
}

export function Transactional(): MethodDecorator {
    return (_target, _key, descriptor: PropertyDescriptor) => {
        const original = descriptor.value as (...args: unknown[]) => Promise<unknown>;

        descriptor.value = function (this: unknown, ...args: unknown[]) {
            if (transactionStorage.getStore())
                return original.apply(this, args);

            return (db() as Kysely<unknown>).transaction().execute((trx) => transactionStorage.run(trx, () => original.apply(this, args)));
        };

        return descriptor;
    };
}
