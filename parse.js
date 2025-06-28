var fs = require('fs');
var SparqlParser = require('sparqljs').Parser;

// Check if an input argument is provided
if (process.argv.length <= 2) {
    console.log("Usage: " + __filename + " <SPARQL_QUERY_STRING>");
    process.exit(-1);
}

var input = process.argv[2];
var parser = new SparqlParser();

try {
    var parsedQuery = parser.parse(input);
    var output = JSON.stringify(parsedQuery, null, 2);

    fs.writeFile('parsedQueryOutput.json', output, 'utf8', function (err) {
        if (err) {
            console.log("An error occured while writing JSON Object to File.");
            return console.log(err);
        }
        console.log("JSON file has been saved.");
    });
} catch (error) {
    console.error("Error parsing SPARQL query:", error.message);
    // cast an error code
    process.exit(1);
}
