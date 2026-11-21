const fs = require('node:fs')
const ts = require('../../frontend/node_modules/typescript')
const name = process.argv[2]
const input = fs.readFileSync(0, 'utf8')
const source = ts.createSourceFile(name, input, ts.ScriptTarget.Latest, true)
if (source.parseDiagnostics.length) process.exit(2)

const symbols = []
const imports = []
const routes = []
const calls = []
const line = (position) => source.getLineAndCharacterOfPosition(position).line + 1
const text = (node) => node.getText(source).slice(0, 160)

function walk(node, parents = []) {
  let scope = parents
  const namedFunction = ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)
    || ts.isGetAccessor(node) || ts.isSetAccessor(node)
  const variableFunction = ts.isVariableDeclaration(node) && node.initializer
    && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))
  const classDefinition = ts.isClassDeclaration(node)
  if ((namedFunction || variableFunction || classDefinition) && node.name) {
    scope = [...parents, text(node.name)]
    symbols.push({ name: scope.join('.'), kind: classDefinition ? 'class' : 'function',
      start: line(node.getStart(source)), end: line(node.end) })
  }
  if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node))
      && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
    imports.push({ name: node.moduleSpecifier.text, line: line(node.getStart(source)) })
  }
  if (ts.isCallExpression(node)) {
    const target = node.expression
    const first = node.arguments[0]
    if (ts.isIdentifier(target) && target.text === 'require' && first && ts.isStringLiteral(first)) {
      imports.push({ name: first.text, line: line(node.getStart(source)) })
    }
    if (scope.length && ts.isIdentifier(target)) {
      calls.push({ caller: scope.join('.'), name: text(target), line: line(node.getStart(source)) })
    }
    if (ts.isPropertyAccessExpression(target) && ts.isIdentifier(target.expression)
        && ['app', 'router', 'server'].includes(target.expression.text) && first && ts.isStringLiteral(first)
        && ['get', 'post', 'put', 'patch', 'delete'].includes(target.name.text)) {
      routes.push({ method: target.name.text.toUpperCase(), path: first.text.slice(0, 200),
        name: node.arguments[1] && ts.isIdentifier(node.arguments[1]) ? node.arguments[1].text : 'handler',
        line: line(node.getStart(source)) })
    }
  }
  ts.forEachChild(node, (child) => walk(child, scope))
}

walk(source)
process.stdout.write(JSON.stringify({ symbols: symbols.slice(0, 180), imports: imports.slice(0, 180),
  routes: routes.slice(0, 100), calls: calls.slice(0, 220) }))
