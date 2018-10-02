$(function() {
	function dismiss_visible_quarters_menu() {
		$("#visible_quarters_control").toggle(false);
	};

	function toggle_visible_quarters_menu() {
		$("#visible_quarters_control").toggle();
	};
	$("#visible_quarters_label").click(toggle_visible_quarters_menu);

	/* Dismiss visible quarters menu whenever clicks on other inputs
	   happen outside the menu */
	$("#content td,th,h1").not("#visible_quarters_label").click(function(e) {
		if ($(this).parents("#visible_quarters_label").length == 0 &&
			$(e.target).parents("#visible_quarters_control").length == 0) {
			dismiss_visible_quarters_menu();
		}
	});


	function show_hide_quarter_column(checkbox) {
		var qtr = $(checkbox).data('quarter');
		$(".players th[data-quarter='" + qtr + "'], " +
			".players td[data-quarter='" + qtr + "']").toggle(checkbox.checked);
	};
	$("input.visibleQtrFlag").change(function() {
		show_hide_quarter_column(this);
	});

	function report_edit_outcome(inputelem) {
		return function(data) {
			if (data["status"] !== 0) {
				console.log(data);
				$.notify(data["message"], data["status"]);
				$(inputelem).removeClass('good').addClass('bad');
			}
			else {
				$(inputelem).removeClass('bad').addClass('good');
			}
		}
	};

	function update_text_field() {
		var playerId = $(this).parents("tr[data-playerId]").data('playerid'),
			columnName = $(this).data('columnname');
		$.post("/players", {
			operation: 'set_' + columnName,
			playerId: playerId,
			value: $(this).val()
		}, report_edit_outcome(this), 'json');
	}
	$("table.players input[data-columnName]").change(update_text_field);

	function update_quarter_membership() {
		var playerId = $(this).parents("tr[data-playerId]").data('playerid'),
			quarter = $(this).data('quarter'),
			reporter = report_edit_outcome(this);;
		$.post("/players", {
			operation: 'set_Membership',
			playerId: playerId,
			quarter: quarter,
			value: $(this).prop("checked")
		}, function(data) {
			reporter(data);
			update_total_members(quarter);
		}, 'json');
	};

	function update_total_members(quarter) {
		$('.totalmembers[data-quarter="' + quarter + '"]').text(
			' : ' +
			$('.membershipFlag[data-quarter="' + quarter + '"]:checked').length)
	};

	$("table.players input.membershipFlag").change(update_quarter_membership);
	$("input.visibleQtrFlag").each(function(i, e) {
		update_total_members($(this).data("quarter"))
	});

	/* Initialize status of control widgets */
	$("#visible_quarters_control").toggle(false);
	$("input.visibleQtrFlag").each(function() {
		show_hide_quarter_column(this);
	});
	$("input.membershipFlag").hover(
		function() {
			$(this).after("<div class='tooltip'>" + $(this).data('quarter') +
				"</div>");
		},
		function() {
			$(this).parents("td").find("input.membershipFlag + .tooltip").remove();
		});
});
