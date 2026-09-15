import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const sql=require('../../atlas/atlas-plugin/workbench/validation/sql.js');
const codes=text=>sql.validateGeneratedSql(text).map(issue=>issue.code);
test('generated SQL uses two-part physical sources and self-contained temporary stages',()=>{
 assert.deepEqual(codes('CREATE OR REPLACE TEMP VIEW prepare AS SELECT CustomerID, SourceSystemID FROM bronze.Customer; SELECT CustomerID, SourceSystemID FROM prepare;'),[]);
 assert.deepEqual(codes('SELECT Quantity * Price AS Amount, SourceSystemID FROM silver.OrderLine'),[]);
 assert.deepEqual(codes('SELECT COUNT(*) AS Total, SourceSystemID FROM silver.OrderLine GROUP BY SourceSystemID'),[]);
});
test('transformation qualification differs from governed validation SQL',()=>{
 assert.ok(codes('SELECT CustomerID FROM catalog.silver.Customer').includes('code.stage-flow'));
 assert.equal(sql.validateReadSql('SELECT CustomerID FROM catalog.silver.Customer').valid,true);
 assert.equal(sql.validateReadSql('SELECT CustomerID FROM silver.Customer').valid,false);
});
test('qualification includes comma joins, nested inputs and every identifier part',()=>{
 for(const text of ['SELECT a.ID FROM bronze.A a, Unknown b','SELECT a.ID FROM bronze.A a JOIN (SELECT ID FROM Unknown) b ON a.ID=b.ID','SELECT ID FROM a.b.c.d']) assert.ok(codes(text).includes('code.stage-flow'));
 assert.deepEqual(codes('SELECT a.ID, COALESCE(a.Name, b.Name) AS Name FROM bronze . A a, bronze.B b WHERE a.ID=b.ID'),[]);
 assert.deepEqual(codes('CREATE OR REPLACE TEMP VIEW v AS WITH a AS (SELECT ID FROM bronze.A), b AS (SELECT ID FROM bronze.B) SELECT a.ID FROM a JOIN b ON a.ID=b.ID; SELECT ID FROM v'),[]);
});
test('missing, forward, duplicate and qualified temporary stages are rejected',()=>{
 for(const text of ['SELECT CustomerID FROM prepare','CREATE OR REPLACE TEMP VIEW v AS SELECT x FROM later; SELECT x FROM v','CREATE OR REPLACE TEMP VIEW v AS SELECT x FROM bronze.X; CREATE OR REPLACE TEMP VIEW v AS SELECT x FROM bronze.Y; SELECT x FROM v']) assert.ok(codes(text).includes('code.stage-flow'));
 assert.ok(codes('CREATE OR REPLACE TEMP VIEW bronze.v AS SELECT x FROM bronze.X; SELECT x FROM bronze.v').includes('code.statements'));
});
test('final projection has no unqualified or qualified wildcard',()=>{
 for(const text of ['SELECT * FROM bronze.X','SELECT x.* FROM bronze.X AS x','SELECT DISTINCT * FROM bronze.X','SELECT ID FROM bronze.X UNION ALL SELECT * FROM bronze.Y','SELECT x.* EXCEPT(secret) FROM bronze.X AS x']) assert.ok(codes(text).includes('code.projection'));
});
test('writes, persistent DDL, commands, secret reads and prose do not enter transformations',()=>{
 for(const text of ['INSERT INTO silver.X SELECT a FROM bronze.X','CREATE TABLE silver.X AS SELECT a FROM bronze.X','USE CATALOG X; SELECT x FROM silver.X','SELECT secret(\'scope\',\'name\') AS x','```sql\nSELECT x FROM silver.X\n```','-- commentary\nSELECT x FROM silver.X']) assert.ok(codes(text).includes('code.statements'),text);
 assert.deepEqual(codes("SELECT 'delete; -- literal' AS Label, SourceSystemID FROM silver.X"),[]);
});
test('unclosed strings are rejected, quoted identifiers are not mistaken for write keywords',()=>{
 assert.ok(codes("SELECT 'unclosed FROM silver.X").includes('code.statements'));
 assert.deepEqual(codes('SELECT `Update`, SourceSystemID FROM silver.X'),[]);
});
