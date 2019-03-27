$(function() {
	var statsTemplate, ranks = ["1st", "2nd", "3rd", "4th", "5th"];

	$.get("/static/mustache/playerstats.mst", function(data) {
		statsTemplate = data;
		Mustache.parse(statsTemplate);
		var parts = document.URL.split('/');
		for (j = 0; j < parts.length; j++) {
			if (parts[j] == 'playerstats') break;
		}
		if (j >= parts.length - 1) {
			$.notify('Unable to determine player for stats')
		}
		else {
			player = parts.slice(j + 1).join('/');
			getData(player);
		}
	});

	function registerFormCallbacks() {
		if ($("#player-update").length > 0) {
			// Initializes and creates emoji set from sprite sheet
			if (window.emojiPicker === undefined)
				window.emojiPicker = new EmojiPicker({
					emojiable_selector: '[data-emojiable=true]',
					assetsPath: 'https://cdnjs.cloudflare.com/ajax/libs/emoji-picker/1.1.5/img/',
					popupButtonClasses: 'fa fa-smile-o'
				});
			// Finds all elements with `emojiable_selector` and converts them to rich emoji input fields
			// You may want to delay this step if you have dynamically created input fields that appear later in the loading process
			// It can be called as many times as necessary; previously converted input fields will not be converted again
			window.emojiPicker.discover();
			$(".emoji-wysiwyg-editor").height("");
			var name1 = $("#player-name").val(),
				meetupname1 = $("#player-meetup-name").val(),
				symbol1 = $("#player-symbol").val();
			var changePlayer = function() {
				$("#update-player").prop(
					"disabled",
					name1 === $("#player-name").val() &&
					meetupname1 === $("#player-meetup-name").val() &&
					symbol1 === $("#player-symbol").val()
				);
			};
			$("#player-update input").keyup(changePlayer);
			var observer = new MutationObserver(function(mutationsList) {
				for (var mutation of mutationsList) {
					if (mutation.type == 'childList') {
						var text = $(mutation.target).text();
						// Temporary disconnect observer so we can
						// change the text without looping infinitely.
						$("#player-symbol").val(text);
						changePlayer();
					}
				}
			});
			$("#player-update .emoji-wysiwyg-editor").each(function(i, elem) {
				var config = {
					attributes: true,
					childList: true,
					subtree: true
				};
				observer.observe(elem, config);
			});
		}
	}

	function getData(player) {
		$.getJSON("/playerstatsdata/" + player, function(data) {
			if (data.status != 0) {
				$.notify(data.error);
			}
			else {
				$("#playerstats").html(Mustache.render(statsTemplate, data));
				registerFormCallbacks();
				d3.selectAll(".playerstatperiod").each(function(d, i) {
					drawData(d3.select(this).select('svg'),
						d3.select(this).select('.rankpielegend'),
						data['playerstats'][i]['rank_histogram']);
				})
			}
		});
	}

	function drawData(svg_selection, legend_selection, data) {
		var rect = svg_selection.nodes()[0].getBoundingClientRect(),
			width = rect.width || 800,
			height = rect.height || 500,
			outerRadius = Math.min(height, width) / 2 - 10,
			innerRadius = outerRadius / 3,
			labelInnerRadius = outerRadius * 0.5,
			path = d3.arc().innerRadius(innerRadius).outerRadius(outerRadius),
			label = d3.arc().innerRadius(labelInnerRadius).outerRadius(
				outerRadius),
			nonzero = data.filter(function(d) {
				return d.count > 0
			}),
			arcs = d3.pie().sort(null).value(function(d) {
				return d.count
			})(
				nonzero),
			g = svg_selection.html(""). // Remove any error message
		append("g"). // Make group node in svg
		attr("class", "rankpiechart"). // for pie chart
		attr("transform", // w/ transform
			"translate(" + width / 2 + "," + height / 2 + ")");
		// Create pie slices for each rank with a non-zero count
		g.selectAll(".arc").data(arcs).enter().
		append("g").classed("arc", true).append("path").attr("d", path).
		attr("class", function(d) {
			return "rank_" + d.data.rank + "_path rank_path"
		});
		// Label each slice near the outer edge with that rank's count
		g.selectAll("text").data(arcs).enter().
		append("text").attr("transform", function(d) {
			return "translate(" + label.centroid(d) + ")";
		}).
		attr("dy", "0.35em").attr("dx", function(d) {
			return ((d.data.count + "").length / -2.0 + 0.2) + 'em';
		}).
		text(function(d) {
			return d.data.count
		}).
		attr("class", function(d) {
			return "rank_" + d.data.rank + "_count rank_count"
		});
		var columns = ["rank", "count"];

		// Build a table for the legend that shows all the ranks and counts
		var rows = legend_selection.selectAll("tr").data(data).enter().
		append("tr"),
			cells = rows.selectAll("td").
		data(function(row) {
			return columns.map(function(col) {
				return {
					column: col,
					value: row[col]
				};
			})
		}).
		enter().append("td").
		attr("class", function(d) {
			return d.column + "_" + d.value + "_label " +
				d.column + "_label"
		}).text(function(d) {
			return d.column == 'rank' ? ranks[d.value - 1] : d.value
		});
	}
});
